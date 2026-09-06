# Glossary — backend

**Read this when** a word in the backend documentation means nothing to you.

Terms shared with the frontend — API, CORS, encryption, hashing, HMAC,
crypto-shredding, tokens, containers, and so on — are in the
[shared glossary](../../docs/GLOSSARY.md). This file covers what is specific to
the Python service.

---

## Python and its tools

**uv** — the tool that installs Python itself and the libraries this project
needs, into an isolated folder. Replaces the older `pip` and `venv` commands.

**Virtual environment (`.venv`)** — a private folder holding this project's
libraries, so they never collide with another project's. Created by `uv sync`.

**`pyproject.toml`** — the file describing the project: its name, which Python
version it needs, and which libraries. `uv` reads it.

**Optional extra** — a group of libraries installed only if asked for.
`uv sync --extra voice` adds speech-to-text, which is several hundred megabytes
and not needed to type.

**FastAPI** — the web framework. Receives requests, validates them, and
produces the Swagger documentation automatically.

**Uvicorn** — the program that actually listens on a network port and hands
requests to FastAPI. FastAPI is the application; uvicorn is the engine.

**Pydantic** — the library that declares and enforces the exact shape of data.
The same declaration validates requests and generates the documentation, so the
two cannot drift apart.

**structlog** — the logging library. Produces log lines as sets of named fields
rather than sentences, which is what makes the redaction filter possible.

**pytest** — the test runner. **Fixture** — a reusable piece of test setup.

**ruff** — the linter and formatter. **mypy** — the type checker.

**Alembic** — the migration runner from the SQLAlchemy project. Recommended
here, but **without** its autogenerate feature, which cannot see stored
procedures and would offer to convert ciphertext columns to text.

**Faker** — generates realistic invented people for the seed script.

**faster-whisper** — the speech-to-text library. An efficient implementation of
OpenAI's open-source Whisper model that runs on an ordinary processor with no
network access.

**httpx** — the HTTP client used for outbound calls, wrapped in our SSRF guard.

**argon2-cffi** — the password hashing library.

**boto3** — the AWS library, used for KMS. Only needed in Phase 2.

---

## Python language terms

**Async / await** — a way of writing code that can start something slow, put it
aside, and do other work while waiting. Essential here because a Gemini call
takes seconds and the server must serve other players during it.

**Blocking call** — one that stops everything until it finishes. Inside async
code this freezes the entire server, so blocking calls are pushed onto worker
threads with `asyncio.to_thread`.

**Type hint** — a note saying what kind of value something is, e.g.
`user_id: UUID`. Checked by mypy; not enforced at runtime.

**Decorator** — the `@something` line above a function, modifying it.
`@router.post(...)` registers a function as an endpoint.

**Dataclass** — a class that mostly just holds values, with the boilerplate
generated.

**Protocol** — a description of a shape rather than a base class. Any object
with the right methods satisfies it, which is what lets the development and AWS
key providers be swapped by changing one setting.

**Context variable** — a variable with a separate value per concurrent task.
Used for the correlation identifier, because a plain global would be
overwritten constantly by other requests.

**Docstring** — the text at the top of a function explaining it. Required on
every function in this project, written for a reader who has never programmed.

---

## This project's own vocabulary

**Repository (layer)** — the only code permitted to touch storage. Encrypts on
the way in, decrypts on the way out. Not to be confused with a Git repository.

**Service (layer)** — where the game rules live. Works with plaintext objects
and never touches storage directly.

**Container (dependency)** — the object holding every long-lived service, built
once at startup. Not to be confused with a Docker container.

**Dependency injection** — endpoints declaring what they need rather than
building it. What makes rate limiting impossible to forget.

**Choke point** — a single place every operation of a kind must pass through.
The repository layer is the encryption choke point.

**Correlation identifier** — the random value identifying one request, stamped
on all its log lines and returned to the browser. The primary debugging tool.

**Redaction filter** — the log processor replacing any field not on the
allowlist with a description of its type and length.

**Allowlist (`LOGGABLE_FIELDS`)** — the explicit list of fields that may be
logged. Anything else is censored by default.

**Scrubber** — the code that strips structured personal data from prompts
before they are sent to Google.

**Blind index key** — the secret used to fingerprint email addresses. Held in
AWS Secrets Manager and **never** in the database; its absence there is the
whole defence.

**Daily salt** — the value used to fingerprint IP addresses, derived fresh each
day and never stored, so counters cannot be assembled into a history.

**Wrapped key** — a per-user key encrypted by KMS, safe to store beside the
data it opens.

**AAD (Additional Authenticated Data)** — extra context mixed into the tamper
check but not stored. Binds each ciphertext to its user, table and column, so
values cannot be moved between rows.

**Stub** — behaviour deliberately not implemented. In Phase 1 the session token
is a stub; the password hashing behind it is real.

**Debug capture** — the player's opt-in switch storing prompt content,
encrypted under their own key, for at most 48 hours.

**Support grant** — a time-boxed, audited permission to decrypt one user's
records, which also writes an entry into that user's own visible activity log.

**Break-glass** — the emergency procedure for access that is normally denied.
Every use is alerted on.

---

## Database column suffixes

Three suffixes carry meaning throughout the schema and the code:

| Suffix | Means | Example |
|---|---|---|
| `_ct` | Ciphertext — bytes, unreadable without a key | `email_ct` |
| `_bidx` | Blind index — a searchable keyed fingerprint | `email_bidx` |
| `_hmac` | A digest used for counting, not lookup | `ip_hmac` |

Seeing `_ct` should immediately tell a reader "these are bytes; do not try to
print them".

---

## Error codes the API returns

Stable strings the frontend branches on. The wording of messages may change;
these do not.

| Code | Means |
|---|---|
| `validation_failed` | The submitted data was unacceptable. Names the fields, never their values |
| `invalid_credentials` | Sign-in failed. Deliberately identical whether or not the account exists |
| `xsrf_failed` | The cross-site request forgery token was missing or wrong |
| `rate_limited` | Too many requests. `Retry-After` says how long to wait |
| `ai_quota_exhausted` | The Gemini free allowance is spent |
| `upstream_ai_error` | Gemini failed for some other reason |
| `upstream_timeout` | Gemini did not answer in time. Not retried |
| `upstream_unreachable` | Could not connect to Gemini at all |
| `content_blocked` | A safety filter stopped the model responding |
| `model_not_found` | The configured model is not available to this key |
| `not_found` | No such resource — or it belongs to someone else |
| `stt_unavailable` | Speech-to-text is off or not installed |
| `audio_too_large` / `audio_too_long` / `audio_unreadable` | The recording was rejected |
| `internal_error` | Something unexpected. Quote the correlation identifier |
