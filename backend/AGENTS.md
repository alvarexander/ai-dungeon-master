# AGENTS.md — Backend

The Python service behind the AI Dungeon Master. It receives what a player
types or says, asks Google Gemini for the Dungeon Master's reply, and stores
the conversation encrypted. It is the only part of the system that holds an AI
key, an encryption key, or any personal data in readable form.

**Read [SYSTEM_GUIDE.md](../SYSTEM_GUIDE.md) first for anything that spans both
repositories** — the API contract, the shared privacy boundary, and what
crosses the network. It is authoritative where this file and it disagree.

---

## Hard constraints — never violate these

1. **Passwords are hashed with Argon2id and never stored.** This never becomes
   encryption — see [ADR-003](../docs/DECISIONS_PRIVACY.md) for why that
   distinction matters.
2. **All storage access goes through `app/repositories/`.** Never write SQL in
   a service or an endpoint. Every read includes the owner in the query, so one
   account cannot reach another's rows by guessing an identifier.
3. **Every SQL query uses named parameters**, never string joining. That is
   what makes SQL injection impossible rather than unlikely.
4. **Never log a credential, and never log a request body.** Event names are
   fixed strings; variables go in named fields. `log.info(f"...{email}")` bakes
   the value into the message where nothing can inspect it.
5. **No personal data in URLs, query strings, or path parameters.** Opaque
   identifiers only. URLs reach access logs, browser history and `Referer`
   headers.
6. **No real personal data in Swagger examples, test fixtures, or seed data.**
   Use `example.com`, which IANA reserves for documentation.
7. **All outbound HTTP goes through `SafeHttpClient`.** Never use `httpx` or
   `requests` directly — that would bypass the SSRF guard.
8. **Every new function gets a docstring** written for a reader who has never
   programmed. Explain why, not only what.
9. **No AI attribution in commits.** No `Co-Authored-By`, no "generated with"
   lines, no tool footers.
10. **Changing the schema or telemetry means updating the matching document in
    the same commit.**
11. **The backend stays a single deployable.** One FastAPI application, one
    container, one process. Do not split it into microservices, and do not add
    a message broker, a task queue or an API gateway. `routes/`, `services/`
    and `repositories/` are layers *inside* one program — ordinary function
    calls, not network calls. This is a deliberate constraint: the person
    running this is new to application development, and a monolith has one
    thing to deploy, one set of logs, and one place a request can fail.

---

## Local setup

```bash
uv sync --extra voice          # omit --extra voice if the download fails
cp .env.example .env           # then paste a Gemini key into it
uv run uvicorn app.main:app --reload --port 8000
```

Swagger documentation: <http://127.0.0.1:8000/docs>

```bash
uv run pytest                  # 88 tests
uv run ruff check app tests    # lint
uv run mypy app                # type check
```

Full instructions, including a PyCharm run configuration:
[RUNNING.md](../RUNNING.md).

---

## Layout

```
app/
  main.py            application assembly, middleware order
  config.py          settings; refuses to start if production is unsafe
  api/               routes (HTTP only) and dependency injection
  services/          game rules, Gemini, transcription, analytics
  repositories/      the ONLY code that touches storage; encrypts here
  core/security/     password hashing, XSRF, SSRF protection
  core/              logging, rate limiting, errors, correlation IDs
  schemas/           Pydantic request and response models
migrations/          numbered SQL
scripts/             migrate, seed synthetic data, check Gemini models
```

**Dependency rule:** routes → services → repositories. Never backwards.

---

## Documentation index

| File | Read it when |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | You need the layer boundaries, request lifecycle, or trust boundary |
| [CONVENTIONS.md](docs/CONVENTIONS.md) | You are writing code and want the house style |
| [DATABASE.md](docs/DATABASE.md) | You need the schema, a query, or a migration |
| [SECURITY.md](docs/SECURITY.md) | You are touching passwords, XSRF, SSRF, or rate limits |
| [OBSERVABILITY.md](docs/OBSERVABILITY.md) | You are adding logging, analytics, or debugging a report |
| [TESTING.md](docs/TESTING.md) | You are writing tests or need the seed script |
| [GEMINI.md](docs/GEMINI.md) | You need an API key, the quotas, or the DM prompt |
| [GLOSSARY.md](docs/GLOSSARY.md) | A word here means nothing to you |

---

## Phase 1 status

Two things are deliberately not real, and the application **refuses to start**
with either when `APP_ENV=production`:

- **Authentication.** Registration and Argon2id password checking are genuinely
  implemented. The session token is a placeholder that is not verified.
- **Storage.** In-memory by default, so everything is lost on restart. MySQL
  works — set `REPOSITORY_BACKEND=mysql`; see
  [docs/LOCAL_MYSQL.md](../docs/LOCAL_MYSQL.md).

---

## Definition of done

- `uv run pytest` passes.
- `uv run ruff check app tests` is clean.
- `uv run mypy app` is clean.
- Every new function has a beginner-facing docstring.
- Any schema or telemetry change updated its document in the same commit.
- No credential reaches a log, and no personal data reaches a URL.
