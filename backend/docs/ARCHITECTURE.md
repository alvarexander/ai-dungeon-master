# Backend Architecture

**Read this when** you need to know how the backend is organised — which layer
does what, what happens to a request from arrival to reply, and where
encryption sits relative to storage. For the system as a whole, including the
frontend and the clouds, read [ARCHITECTURE.md](../../ARCHITECTURE.md) at the
project root.

---

## This is a monolith, on purpose

**One application, one container, one process.** `uvicorn app.main:app` is the
whole backend. There is no message broker, no task queue, no API gateway, and
no service that calls another service over a network.

Worth saying explicitly because the folder structure can be misread. `routes/`,
`services/` and `repositories/` look like they could be three deployables. They
are not — they are **layers inside one program**, and calls between them are
ordinary Python function calls that never touch a network.

**Why a monolith here.** Microservices buy independent deployment and
independent scaling, and charge for it in operational complexity: several
things to deploy, several sets of logs, network calls that can fail between
your own components, and distributed transactions. For one developer new to
application development, running one application with one log stream, that
trade is firmly the wrong way round.

There is also a specific benefit for *this* application. Encryption depends on
a choke point — the repository layer being the only path to storage. That is
easy to guarantee inside one process and considerably harder across a network
boundary, where a second service could reach storage another way.

**If you ever do split it**, the layer boundaries below are where the seams
already are. But do not do it because the folder structure suggests it; do it
because a specific part genuinely needs to scale separately, and be honest that
you are buying that with operational complexity.

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

Two things follow from it.

**Storage decisions live in one place.** Swapping the in-memory store for MySQL
changes only the classes in `repositories/`, and no service or endpoint is
aware it happened.

**Ownership checks live in one place.** Every read includes the owner in the
query rather than checking afterwards, so "can this account see this row?" is
answered once instead of in every endpoint — and cannot be forgotten in the
next one somebody writes.

### What belongs in each layer

| Layer | Belongs here | Does not belong here |
|---|---|---|
| **Routes** (`app/api/v1/`) | Reading the request, declaring the response model, HTTP status codes | Game rules, arithmetic, storage access |
| **Services** (`app/services/`) | Game rules, prompt assembly, orchestration | SQL, HTTP status codes, encryption |
| **Repositories** (`app/repositories/`) | All storage access, ownership checks | Business decisions |

A useful test: if a function mentions both a status code and a dice roll, it is
in the wrong place.

---

## Two storage backends

`REPOSITORY_BACKEND` chooses between them:

| Value | What it is | Survives a restart? |
|---|---|---|
| `memory` (default) | Python dictionaries | No |
| `mysql` | A real database, plain SQL | Yes |

Both satisfy the interfaces in `repositories/base.py`, so nothing above that
layer knows which one it got. The in-memory store is the default so that the
application runs with nothing installed — requiring a database installation
before anything works is the point at which newcomers give up.

`sql.py` uses hand-written SQL rather than an object mapper. Every query can be
read, copied into a database client, and run. When something is slow or wrong,
the thing to look at is right there rather than behind generated SQL. See
[ADR-014](../../docs/DECISIONS_PLATFORM.md).

**The one rule with no exceptions:** every query uses named parameters, never
string joining.

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

## How data is protected

There is no application-layer encryption. Personal data is stored as readable
values and protected by access control: TLS in transit, a firewall in front of
the database, and a database user that can read and write rows but cannot
change the schema.

**Passwords are the exception** — hashed with Argon2id, never recoverable.

**Anyone who can query the database can read email addresses and
conversations.** That is the honest consequence, and it makes the database
credentials the most important secret in the system. See
[SECURITY.md](SECURITY.md) and [ADR-002](../../docs/DECISIONS_PRIVACY.md).

---

## What is not finished

| | Now | Next |
|---|---|---|
| Sessions | Unsigned placeholder token | Signed, expiring, stored as a hash |
| Password reset | Not implemented | Needs email delivery |
| Rate limiting | One process's memory | Database-backed, before running two machines |

The application refuses to start with stubbed authentication when
`APP_ENV=production`.

---

## Related documents

- [CONVENTIONS.md](CONVENTIONS.md) — house style.
- [SECURITY.md](SECURITY.md) — how the encryption is implemented.
- [DATABASE.md](DATABASE.md) — the schema.
- [OBSERVABILITY.md](OBSERVABILITY.md) — the two telemetry planes.
- [Architecture decisions](../../docs/ARCHITECTURE_DECISIONS.md) — why.
