# Backend Security

**Read this when** you are touching authentication, XSRF, SSRF, rate limiting,
input validation, or anything to do with how data is protected.

For the overall posture and what a breach would expose, read
[PRIVACY.md](../../PRIVACY.md) first. This file is the implementation detail.

---

## The posture, in one paragraph

Personal data is stored as readable values in the database. It is protected by
controlling who can reach it: TLS in transit, a firewall in front of the
database, an application user with limited rights, and the provider's disk
encryption. **Passwords are the exception** — they are hashed with Argon2id and
are not recoverable by anybody.

That is what a well-built ordinary web application does. An earlier version of
this project encrypted every personal column with per-user keys managed by AWS
KMS; that was removed deliberately, and
[ADR-002](../../docs/DECISIONS_PRIVACY.md) records why.

---

## Passwords

**Argon2id**, `time_cost=3`, `memory_cost=65536` (64 MB), `parallelism=2` —
OWASP's recommended baseline, tuned for a small server.

The library generates a random salt per password and stores it inside the
resulting string, so there is nothing to manage. Two users with the same
password get different hashes and cannot be attacked together.

**64 MB is charged per concurrent login**, so ten simultaneous sign-ins is
640 MB. That is the number that interacts with the server's memory size, and
the reason the Fly.io machine is 1 GB rather than 256 MB.

Two supporting measures in `app/core/security/passwords.py`:

- **`verify_dummy`** spends the same time when no account matches. Without it,
  an unknown email returns in a millisecond and a known one in 300, and an
  attacker enumerates your users with a stopwatch. This is a side channel, and
  side channels are easy to leave open by accident.
- **`needs_rehash`** upgrades old hashes at the next sign-in when the cost
  parameters rise, with no password reset and no announcement.

---

## Rate limits, and the reasoning for each

| Scope | Limit | Why this number |
|---|---|---|
| `login` | 5 / 15 min | Makes password guessing impractical, and caps account enumeration at 20 attempts an hour. High enough that a person mistyping three times is unaffected |
| `register` | 3 / hour | Registration reveals whether an email is already in use, so it is the other enumeration surface. Also stops automated signups burning the AI quota |
| `password_reset` | 3 / hour | Same enumeration risk, and each attempt would send an email |
| `chat` | 20 / min | Far above natural play; well below what would exhaust a daily AI allowance in one sitting |
| `stt` | 10 / min | Transcription is the most processor-intensive thing the server does. Protects responsiveness as much as it prevents abuse |
| `ip_global` | 300 / min | A backstop against broad scraping. High enough never to affect a real person |

All configurable in `.env`, all parsed at startup — so a typo stops the
application rather than silently disabling a limit.

Limits are declared as endpoint dependencies:

```python
dependencies=[Depends(rate_limit("login"))]
```

The check runs before the endpoint body. There is no way to write the endpoint
and then forget to call the limiter, because calling it is not the endpoint's
job.

**Before running more than one machine:** the counters live in one process's
memory, so two machines keep separate tallies and every limit silently doubles.
Move them to the database first.

---

## Authentication, and what is not real yet

**Genuinely implemented:** registration, Argon2id hashing and verification,
uniform failure messages, timing equalisation, and rate limiting.

**Not implemented:** the session. `issue_token` returns `stub.<user_id>` and
`user_id_from_token` believes it. There is no signature, no expiry, and no
revocation — anyone can mint one for any account by typing it.

That is why `AUTH_MODE=stub` causes the application to **refuse to start** when
`APP_ENV=production`. The screens can be clicked through today; the door is not
actually locked, and the application will not pretend otherwise on a real
server.

Two protections that *are* real and are easy to omit:

1. **Identical failure.** Whether the account does not exist, the password is
   wrong, or the account is suspended, the caller gets the same 401 with the
   same wording. Anything more specific is a map of who is registered.
2. **Not-found beats forbidden.** Requesting someone else's campaign returns
   404, not 403. A 403 would confirm the identifier is real.

---

## XSRF protection

Double-submit cookie. The server sets a random token in a cookie JavaScript can
read; the client echoes it in `X-XSRF-TOKEN`; the server compares them with
`hmac.compare_digest` — a constant-time comparison, so it does not leak how much
of the token was guessed.

**The deployment constraint, which catches nearly everyone.** A browser will not
let a page read a cookie from a different domain. Locally both are `localhost`
and cookies ignore ports, so it just works. In production you must arrange:

```
frontend   https://app.example.com     (Hostinger)
backend    https://api.example.com     (Fly.io)
COOKIE_DOMAIN=.example.com
```

If the backend stays on a `*.fly.dev` address while the frontend is on your own
domain, the browser treats them as unrelated sites and **every state-changing
request fails with a 403.** Plan for it; do not debug it on launch day.

**Two client-side traps:**

- Angular's built-in XSRF support only attaches the token to *relative* URLs,
  and every one of our requests is absolute. Hence the custom interceptor in
  `frontend/src/app/core/http/xsrf.interceptor.ts`.
- Swagger's "Try it out" does not know about the token either. Rather than
  exempt `/docs` — which would leave a hole in production — the documentation
  page attaches the header itself (`app/api/docs.py`).

---

## SSRF protection

Every outbound request goes through `SafeHttpClient`, which applies three
checks:

1. **HTTPS only.** Plain HTTP would expose prompt content on the network path.
2. **Hostname allowlist**, derived from `GEMINI_BASE_URL` so the client and its
   guard cannot disagree. An allowlist, not a blocklist: unknown destinations
   are refused rather than permitted-unless-recognised.
3. **Resolved address must be public.** Catches an allowlisted name made to
   point at `127.0.0.1`, `10.x`, or `169.254.169.254` — the cloud metadata
   address that hands out credentials.

**Redirects are refused outright**, since following one means visiting an
address that was never checked.

The DNS lookup runs on a worker thread. `socket.getaddrinfo` blocks, and a
blocking call inside asynchronous code freezes the entire server — every other
player's request stops until it returns. That was a real bug in this codebase,
found by noticing a failing request took fifteen seconds longer than its own
timeout.

**The known limit, recorded rather than glossed over:** DNS rebinding, where a
name resolves safely when checked and unsafely a moment later when connecting.
Closing it completely means pinning the connection to an address, which
conflicts with certificate validation. Given that check 2 restricts
destinations to fixed Google hostnames, the residual risk is very small — but
it is real.

**Never use `httpx` or `requests` directly.** That bypasses all three checks.

---

## Input validation

Pydantic validates every request before any of our code runs — types, lengths,
enums, and unknown-field rejection.

| Field | Bound | Reason |
|---|---|---|
| `message` | 4000 chars | Caps token cost per turn; stops one message pushing the history out of the model's memory |
| `password` | 12–200 chars | Floor for strength; ceiling so a huge submission cannot force expensive hashing — a denial of service through the password field |
| `username` | 3–32, `[A-Za-z0-9_-]` | Narrow on purpose, so it cannot hold an email address or a sentence |
| ability scores | 1–30 | The rules' limits, and stops a value large enough to break arithmetic downstream |
| audio upload | 10 MB, 120 s | Bounds memory and processor time on the most expensive endpoint |

**Validation errors never echo the submitted value.** FastAPI's default
includes it, which would put a malformed email into the response *and* the logs.
The handler in `app/core/errors.py` reports the field name and the problem type
only. Pinned by a test.

---

## SQL injection

Every query in `app/repositories/sql.py` uses named parameters:

```python
text("SELECT ... FROM users WHERE email = :email"), {"email": email}
```

The driver sends the query and the values separately, so a value can never be
read as part of the query. **Never build SQL by joining strings**, however
certain you are about the input. This is the most common serious web
vulnerability, and parameters make it impossible rather than unlikely.

---

## Database access control

The application connects as a user with rights to one database and no ability
to change its structure:

```sql
GRANT SELECT, INSERT, UPDATE, DELETE ON dungeon_master.* TO 'dm'@'localhost';
```

Note what is absent: no `CREATE`, no `DROP`, no `ALTER`. Migrations run
separately, by you, with different credentials. **If the running application
cannot drop a table, neither can anyone who compromises it.**

---

## Security headers

Applied to every response by `SecurityHeadersMiddleware`:

| Header | Stops |
|---|---|
| `X-Content-Type-Options: nosniff` | The browser deciding our JSON "looks like" HTML and running it |
| `X-Frame-Options: DENY` | Clickjacking via invisible frames |
| `Referrer-Policy: no-referrer` | Our URLs leaking to sites the user visits next |
| `Permissions-Policy` | Any code running here reaching the microphone or camera |
| `Content-Security-Policy: default-src 'none'` | This API returns JSON only, so nothing needs to load |
| `Strict-Transport-Security` | Plain HTTP to this host, for two years |

HSTS is sent **only in production**. Sending it locally would make the browser
refuse plain HTTP to `localhost`, which is hard to undo and breaks every other
project on the machine.

---

## Fail-closed startup

`Settings.validate_production_safety` refuses to start when `APP_ENV` is
`production` and any of these remain: stubbed authentication, redaction
disabled, insecure cookies, an `http://` CORS origin, a database without TLS, or
console-format logs.

Crashing at startup is loud and fixable. Running in production with stubbed
authentication is neither.

---

## Secrets

Two, and only two:

| Secret | Local | Production |
|---|---|---|
| `GEMINI_API_KEY` | `.env` | `fly secrets set` |
| `DATABASE_URL` (contains the password) | `.env` | `fly secrets set` |

`.env` is in `.gitignore`. Check `git status` before committing if you are
unsure — a committed secret must be treated as leaked and rotated, because Git
history is permanent and often made public later.

---

## Related documents

- [PRIVACY.md](../../PRIVACY.md) — the posture and what a breach exposes.
- [DATABASE.md](DATABASE.md) — the schema.
- [OBSERVABILITY.md](OBSERVABILITY.md) — logging and analytics.
- [GEMINI.md](GEMINI.md) — API key handling and what Google does with prompts.
