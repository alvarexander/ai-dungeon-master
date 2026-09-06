# Backend Architecture

**Read this when** you need to know how the backend is organised — which layer
does what, what happens to a request from arrival to reply, and where
encryption sits relative to storage. For the system as a whole, including the
frontend and the clouds, read [ARCHITECTURE.md](../../ARCHITECTURE.md) at the
project root.

---

## The three layers

```
        HTTP request
             |
    [ middleware ]      CORS, correlation ID, security headers, XSRF
             |
    [ routes ]          speak HTTP; validate shape; nothing else
             |
    [ services ]        game rules and business rules; plaintext objects
             |
    [ repositories ]    the ONLY code that touches storage; encrypts here
             |
        storage
```

**Dependencies point one way.** A route may call a service. A service may call
a repository. Nothing calls backwards, and nothing skips a layer.

### Why this matters more than usual here

In most projects layering is about tidiness. Here it is a security control.

Because the repository is the **only** door to storage, it is impossible to
save a user's email without passing through the code that encrypts it. There is
no code path that reaches the database another way. Correctness stops depending
on whether whoever writes the next endpoint remembers to encrypt — that is the
whole point of a choke point.

### What belongs in each layer

| Layer | Belongs here | Does not belong here |
|---|---|---|
| **Routes** (`app/api/v1/`) | Reading the request, declaring the response model, HTTP status codes | Game rules, arithmetic, storage access |
| **Services** (`app/services/`) | Game rules, prompt assembly, orchestration | SQL, HTTP status codes, encryption |
| **Repositories** (`app/repositories/`) | Encryption, decryption, storage access | Business decisions |

A useful test: if a function mentions both a status code and a dice roll, it is
in the wrong place.

---

## Where encryption sits relative to the ORM

**Above it.** This is a deliberate choice with a practical consequence.

An ORM (Object Relational Mapper) turns database rows into Python objects. If
encryption happened inside or below it — in a model hook, or in a database
trigger — then plaintext would already have travelled to the database server
before being encrypted. It would appear in query logs, in slow-query logs, and
in any network capture between Fly.io and AWS.

So encryption happens in the repository's mapping functions, before the ORM
sees anything:

```
service          repository                    storage
--------         ----------                    -------
User(            encrypt(email) ------------>  email_ct = b'\x01\x8f...'
  email=         blind_index(email) -------->  email_bidx = b'\x9f\x2c...'
  "a@b.com"      hash already done             password_hash = '$argon2id$...'
)                username passes through --->  username = 'torchbearer'
```

By the time the database sees an email address, it is an opaque block of bytes.

The concrete implementation is `MemoryUserRepository.create` in
`app/repositories/memory.py`. Phase 2 adds a SQL implementation that encrypts at
exactly the same boundary; nothing above it changes.

---

## The life of a request

Take `POST /api/v1/chat/turn`.

1. **CORS middleware.** Outermost, so even a rejected request comes back with
   the headers the browser needs to *read* the rejection. Without this a 403
   from the XSRF layer appears in the browser as an opaque network error.
2. **Correlation middleware.** Assigns a random identifier, or accepts a
   supplied one if it is short and alphanumeric. A supplied value is never
   trusted as-is — an attacker could otherwise inject newlines and forge log
   lines.
3. **Security headers middleware.** Adds `nosniff`, `DENY`, a content policy,
   and HSTS in production. Sits outside XSRF so error responses get them too.
4. **XSRF middleware.** Compares the cookie against the header using a
   constant-time comparison. Innermost of the four.
5. **Rate limiting**, declared as a dependency on the route. The caller's
   address is fingerprinted first — the limiter only ever sees 32 opaque bytes.
6. **Pydantic validation.** The request must match `ChatTurnRequest` exactly:
   1 to 4000 characters, no unknown fields. Anything else is rejected before
   our code runs.
7. **The route** calls `GameService.take_turn` and does nothing else of note.
8. **The service** loads history (decrypting), scrubs the outbound prompt,
   calls Gemini, stores both messages (encrypting), and records an analytics
   event.
9. **The response** carries `X-Correlation-ID` so the browser can show it.

Failures anywhere become the standard error envelope — see
`app/core/errors.py`. Nothing leaks a stack trace to the browser.

---

## Dependency injection

Endpoints declare what they need rather than building it:

```python
async def take_turn(
    payload: ChatTurnRequest,
    user: CurrentUser,
    container: ContainerDep,
) -> ChatTurnResponse:
```

Two consequences worth understanding:

- **Security checks cannot be forgotten.** Rate limiting is declared as
  `dependencies=[Depends(rate_limit("chat"))]`. It runs before the endpoint
  body. There is no way to write the endpoint and then forget to call the
  limiter, because calling it is not the endpoint's job.
- **Tests can replace anything.** The Gemini client is swapped for a fake by
  overriding one attribute on the container. No network, no quota spent, no
  test content sent to a third party.

Everything long-lived is built once at startup into a `Container`
(`app/api/deps.py`) and attached to `app.state`. The encryption service in
particular caches unwrapped keys for about five minutes — rebuilding it per
request would mean a key-service call per field.

---

## The Gemini integration boundary

All AI access goes through `app/services/gemini.py`. Nothing else in the
codebase knows Google exists.

That module is hand-written against the REST interface rather than using
Google's Python library, for one reason: the library opens its own network
connections, which would travel around the SSRF guard. A rule with no
exceptions is enforceable; a rule with one is not.

It is also where the observability contract is kept. Every call logs the model,
latency, token counts, finish reason, safety blocks, error code and retry
count — and **never the prompt or the response.**

**Retry behaviour, and one deliberate asymmetry:**

| Failure | Retried? | Why |
|---|---|---|
| 429, 500, 502, 503, 504 | Yes, with backoff and jitter | Genuinely transient |
| Connection refused / unreachable | **No** | It will not be reachable a second later |
| Timeout | **No** | It already consumed the whole waiting budget; retrying turns a 30-second failure into a 95-second one |
| 400, 401, 403, 404 | No | Our request is wrong and will be wrong again |
| SSRF guard refusal | No | Configuration fault or attack; neither improves by retrying |

---

## The trust boundary

**Inside** — holds keys, assumed honest: the running application, AWS KMS.

**Outside** — assumed compromised: the database, every backup, all logs.

```
   INSIDE                         OUTSIDE
   ------                         -------
   backend  ---- ciphertext ---->  MySQL ----> backups
      |                              ^
   AWS KMS                           |
   (master key                  an attacker with
    never leaves)               a full copy reads:
                                usernames, timestamps,
                                counters, enums.
                                Nothing else.
```

**Stated plainly:** this does not defend against someone who compromises the
running server, because that server necessarily holds keys while working. That
is a different and harder attack. Claiming otherwise would be dishonest.

---

## Phase 1 versus Phase 2

| | Phase 1 (now) | Phase 2 |
|---|---|---|
| Storage | In-memory, real encryption, development key | MySQL on RDS |
| Keys | Fixed key in `.env`, loudly flagged | AWS KMS, per-user |
| Sessions | Unsigned placeholder token | Signed, expiring, in `user_sessions` |
| Rate limiting | In this process's memory | `sp_rate_limit_hit` stored procedure |
| Analytics | In memory | `sp_analytics_record`, enum-enforced |

Switching is configuration, not a rewrite, because both sides of each row
satisfy the same interface. The schema and its migrations already exist and are
runnable.

---

## Related documents

- [CONVENTIONS.md](CONVENTIONS.md) — house style.
- [SECURITY.md](SECURITY.md) — how the encryption is implemented.
- [DATABASE.md](DATABASE.md) — the schema.
- [OBSERVABILITY.md](OBSERVABILITY.md) — the two telemetry planes.
- [Architecture decisions](../../docs/ARCHITECTURE_DECISIONS.md) — why.
