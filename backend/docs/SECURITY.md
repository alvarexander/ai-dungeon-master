# Backend Security

**Read this when** you are touching encryption, keys, authentication, XSRF,
SSRF, rate limiting, or input validation. It describes how each is actually
implemented and, where a defence has a limit, says what the limit is.

---

## The threat model

The design assumes one adversary: **someone with a complete copy of the
database.** A leaked snapshot, a stolen backup, a compromised read replica, a
dishonest administrator, or you on a bad day.

That adversary must learn nothing about who the users are.

**Explicitly outside this boundary:** the running application server and the
keys it holds while working. Compromising both the database and a live server
is a different and much harder attack, and this design does not claim to stop
it. Saying otherwise would be dishonest.

---

## Encryption

### The scheme

Application-layer envelope encryption with a key per user.

- **Algorithm:** AES-256-GCM. GCM also detects tampering, so a flipped bit
  causes a loud failure rather than silently corrupted output.
- **Per-user Data Encryption Key**, wrapped by an AWS KMS master key and stored
  in `users.dek_wrapped`.
- **Stored format:** `[1 byte version][12 byte nonce][ciphertext + 16 byte tag]`.
- **Additional authenticated data:** `v1|{user_id}|{table}|{column}`.

That last line is worth pausing on. The AAD is not stored — it is recomputed at
decryption time and mixed into the tamper check. So a value encrypted for
`users.email` will not decrypt as `characters.name`, and a value encrypted for
Alice will not decrypt for Bob. **Ciphertext cannot be relocated**, which
closes an entire category of attack where rows are shuffled rather than read.

Both properties are pinned down by tests in `tests/test_encryption.py`.

### The key hierarchy

| Key | Purpose | Lives | In the database? |
|---|---|---|---|
| KMS master key | Wraps every user key | AWS KMS hardware | Never |
| Per-user key | Encrypts one user's data | Wrapped, in their row | Only wrapped |
| Blind index key | Fingerprints emails | Secrets Manager | **Never** |
| IP salt | Fingerprints addresses, rotates daily | Derived in memory | **Never** |
| Audit key | Encrypts support access reasons | A separate KMS key | Never |

Read that last column again. Nothing in it says "the database". That is the
design.

### Key rotation

Every encrypted row carries `dek_key_version`. Rotating the master key leaves
existing rows readable, because KMS can still unwrap keys made under earlier
generations. New writes use the new version. Rotation is therefore instant and
touches no rows; re-encryption becomes an optional background job at whatever
pace you like, not an outage.

### Where encryption happens

In the repository layer, above the ORM. Plaintext never travels to the database
server, so it cannot appear in query logs or in a network capture between
Fly.io and AWS. See [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Passwords: hashed, never encrypted

**Argon2id**, via `argon2-cffi`, parameters `time_cost=3`,
`memory_cost=65536` (64 MB), `parallelism=2`.

The distinction newcomers get wrong: encryption is reversible, hashing is not.
A password must never be readable by anyone, including us, so it is hashed.
Encrypted passwords would mean that anyone obtaining the key recovers every
password in plaintext — and because people reuse passwords, you would have
handed over their email and bank logins too.

Argon2id is deliberately slow *and* memory-hungry. The memory requirement is
what defeats specialised cracking hardware: you can fit thousands of tiny fast
circuits on a chip, but not thousands of copies of 64 megabytes.

**The 64 MB is charged per concurrent login**, so it interacts directly with
the memory size of the Fly.io machine. Worth remembering before raising it.

Two supporting measures:

- **`verify_dummy`** spends the same time when no account matches. Without it,
  an unknown address returns in a millisecond and a known one in 300 — an
  attacker enumerates your users with a stopwatch.
- **`needs_rehash`** quietly upgrades old hashes at next login as parameters
  rise, with no password reset and no announcement.

---

## The blind index

Login needs to find a user by email. Emails are encrypted, and encrypting the
same address twice gives different bytes, so `WHERE email_ct = ?` can never
match.

The answer is a second column: `HMAC-SHA256(index_key, normalize(email))`,
stored as `BINARY(32)` with a unique index. Deterministic, so it can be
searched; one-way and keyed, so it cannot be reversed.

**What it leaks, precisely:**

1. **Equality.** Two identical fingerprints mean two accounts share an address
   — without revealing which address.
2. **Existence, but only with the key.** Without the index key, a dump cannot
   be tested against a guessed address. With it, any guessable address could
   be checked. This is why the key's absence from the database is the entire
   defence, and why it must never be logged, committed, or copied into a
   spreadsheet.

**The residual exposure is through the live application**, not the dump: a
login endpoint that distinguishes "no such user" from "wrong password" lets an
attacker enumerate accounts one guess at a time. Two mitigations, both
implemented: identical responses either way, and the strictest rate limit in
the application (5 per 15 minutes).

---

## IP addresses

An IP address is personal data — it frequently identifies a household. So rate
limiting counts fingerprints, not addresses:

```
salt_for_today = HMAC(ip_hash_secret, "ip-salt:2026-09-06")
bucket         = HMAC(salt_for_today, ip_address)
```

The salt is **derived** rather than stored, so there is no table of past salts
to steal and no cleanup job to forget. Because it changes daily, yesterday's
counter rows cannot be matched against today's — the counters work for the hour
they are needed and are useless afterwards as a history of anyone's activity.

**The demonstration this design cares about:** the entire abuse-prevention path
runs with zero decryption calls and zero readable identifiers. Comparing
digests needs no key. Privacy and security do not trade off here. Proved in
`tests/test_ratelimit.py::test_the_whole_path_runs_on_a_digest`.

---

## Rate limits, and the reasoning for each

| Scope | Limit | Why this number |
|---|---|---|
| `login` | 5 / 15 min | Makes password guessing impractical, and caps email enumeration through the blind index at 20 attempts an hour. Low enough to bite an attacker, high enough that a person mistyping a password three times is unaffected. |
| `register` | 3 / hour | Registration is the other endpoint that reveals whether an address exists. Also stops automated account creation burning the AI quota. |
| `password_reset` | 3 / hour | Same enumeration risk, plus each attempt would send an email. |
| `chat` | 20 / min | Far above natural play — nobody types twenty messages a minute — and well below what would exhaust a daily AI allowance in one sitting. |
| `stt` | 10 / min | Transcription is the most processor-intensive thing the server does. This protects responsiveness as much as it prevents abuse. |
| `ip_global` | 300 / min | A backstop against broad scraping. High enough never to affect a real person. |

All configurable in `.env`; all parsed at startup, so a typo stops the
application rather than silently disabling a limit.

---

## XSRF protection

Double-submit cookie. The server sets a random token in a cookie JavaScript can
read; the client echoes it in `X-XSRF-TOKEN`; the server compares them with
`hmac.compare_digest` (constant-time, so the comparison does not leak how much
of the token was guessed).

**The deployment constraint, which catches nearly everyone:** a browser will
not let a page read a cookie from a different domain. Locally both are
`localhost` and cookies ignore ports, so it just works. In production you must
arrange:

```
frontend   https://app.example.com     (Hostinger)
backend    https://api.example.com     (Fly.io)
COOKIE_DOMAIN=.example.com
```

If the backend stays on a `*.fly.dev` address while the frontend is on your own
domain, the browser treats them as unrelated sites and **every state-changing
request will fail with a 403.** This is a constraint to design for, not a bug
to debug on launch day.

**Two client-side traps:**

- Angular's built-in XSRF support only attaches the token to *relative* URLs.
  Every one of our requests is absolute. Hence the custom interceptor in
  `frontend/src/app/core/http/xsrf.interceptor.ts`.
- Swagger's "Try it out" does not know about the token either. Rather than
  exempt `/docs` — which would leave a hole in production — the documentation
  page was replaced with one that attaches the header itself
  (`app/api/docs.py`).

---

## SSRF protection

Every outbound request goes through `SafeHttpClient`, which applies three
checks:

1. **HTTPS only.** Plain HTTP would expose prompt content on the network path.
2. **Hostname allowlist**, derived from `GEMINI_BASE_URL` so the client and its
   guard cannot disagree. An allowlist, not a blocklist.
3. **Resolved address must be public.** Catches an allowlisted name made to
   point at `127.0.0.1`, `10.x`, or `169.254.169.254` — the cloud metadata
   address that hands out credentials.

**Redirects are refused outright**, since following one means visiting an
address that was never checked.

**The known limit, recorded rather than glossed over:** DNS rebinding, where a
name resolves safely when checked and unsafely a moment later when connecting.
Closing it completely means pinning the connection to a resolved address, which
conflicts with certificate validation and connection pooling. Given that check
2 already restricts destinations to fixed Google hostnames, the residual risk
is very small — but it is real.

**Never use `httpx` or `requests` directly.** That bypasses all three checks. A
rule with no exceptions is enforceable; a rule with one is not.

---

## Input validation

Pydantic validates every request before any of our code runs — types, lengths,
enums, and unknown-field rejection.

Notable bounds and why they exist:

| Field | Bound | Reason |
|---|---|---|
| `message` | 4000 chars | Caps token cost per turn; stops one message pushing the whole history out of the model's memory |
| `password` | 12–200 chars | Floor for strength; ceiling so a huge submission cannot be used to force expensive hashing |
| `username` | 3–32, `[A-Za-z0-9_-]` | It is stored readable, so it must not be able to hold an email or a sentence |
| ability scores | 1–30 | The rules' limits, and stops a value large enough to break arithmetic downstream |
| audio upload | 10 MB, 120 s | Bounds memory and processor time on the most expensive endpoint |

**Validation errors never echo the submitted value.** FastAPI's default
includes it, which would put a malformed email into the response and the logs.
The handler in `app/core/errors.py` reports the field name and the problem
type only. Pinned by
`tests/test_api_security.py::test_validation_errors_do_not_echo_the_submitted_value`.

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
`production` and any of these remain: a development encryption key, stubbed
authentication, redaction disabled, insecure cookies, an `http://` CORS origin,
a database without TLS, or console-format logs.

Crashing at startup is loud and fixable. Running in production with a
development key is neither.

---

## Related documents

- [DATABASE.md](DATABASE.md) — per-column classification.
- [OBSERVABILITY.md](OBSERVABILITY.md) — redaction and supervised access.
- [GEMINI.md](GEMINI.md) — API key handling and what Google does with prompts.
- [Privacy decisions](../../docs/DECISIONS_PRIVACY.md) — why.
