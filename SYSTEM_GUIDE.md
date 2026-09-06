# System Guide

**Read this when** you need something that spans both repositories: the API
contract between them, the shared privacy boundary, what crosses the network,
and how to deploy the whole thing.

**This file is authoritative** where it and a repository's own `AGENTS.md`
disagree.

---

## The system in one paragraph

An Angular application in the browser sends what a player typed or said to a
Python backend. The backend scrubs recognisable personal data from the message,
asks Google Gemini for the Dungeon Master's reply, stores both messages
encrypted with a key belonging to that one player, and sends the narration
back. In production those two halves live with different hosting companies, and
the database with a third.

For diagrams, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Running both halves locally

Full step-by-step, written for someone who has never done it:
**[RUNNING.md](RUNNING.md)**.

The short version — two terminals:

```bash
cd backend && uv sync --all-extras && cp .env.example .env
# paste a Gemini key into .env, then:
uv run uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend && npm install && npm start
```

Then <http://localhost:4200>. Or, with Docker, one command:
`docker compose up --build`.

---

## The API contract

The backend is authoritative. Its live, generated documentation is at
`/docs` — built from the same Pydantic models that validate every request, so
it cannot drift from what the code does.

The frontend's copy of these shapes is `frontend/src/app/core/api/api.types.ts`.

> **The boundary between the two programs is not type-checked.** A mismatch
> shows up as `undefined` at runtime, not as a build error. **When a Pydantic
> model changes, change the TypeScript type in the same commit.**

### The endpoints

| Method           | Path                                  | Purpose                                 | Status                   |
| ---------------- | ------------------------------------- | --------------------------------------- | ------------------------ |
| GET              | `/health`                             | Is the process alive?                   | Working                  |
| GET              | `/health/ready`                       | Is it configured correctly?             | Working                  |
| GET              | `/api/v1/auth/csrf`                   | Fetch the XSRF token                    | Working                  |
| POST             | `/api/v1/auth/register`               | Create an account                       | Real, except the session |
| POST             | `/api/v1/auth/login`                  | Sign in                                 | Real, except the session |
| POST             | `/api/v1/auth/logout`                 | Sign out                                | Working                  |
| GET              | `/api/v1/auth/me`                     | The current account                     | Working                  |
| POST             | `/api/v1/chat/turn`                   | **Say something to the DM**             | **Working**              |
| GET              | `/api/v1/chat/sessions/{id}/messages` | Read a conversation                     | Working                  |
| GET/POST         | `/api/v1/campaigns`                   | List / create                           | Working                  |
| GET/PATCH/DELETE | `/api/v1/campaigns/{id}`              | One campaign                            | Working                  |
| GET/POST         | `/api/v1/campaigns/{id}/characters`   | List / create                           | Working                  |
| GET/PATCH/DELETE | `/api/v1/characters/{id}`             | One character                           | Working                  |
| GET/PATCH        | `/api/v1/settings`                    | Preferences                             | Working                  |
| GET              | `/api/v1/account/activity`            | The user's own activity log             | Working                  |
| POST             | `/api/v1/account/delete`              | **Delete the account and all its data** | **Working**              |
| POST             | `/api/v1/voice/transcribe`            | Audio to text, locally                  | Working                  |

### Rules that cross the boundary

**Every error looks the same:**

```json
{ "error": { "code": "rate_limited", "message": "…", "correlation_id": "…" } }
```

**Branch on `code`, never on `message`.** Codes are a contract; wording is not.
The full list is in
[backend/docs/GLOSSARY.md](backend/docs/GLOSSARY.md).

**Every response carries `X-Correlation-ID`.** The frontend shows it on error
screens. It is how a problem is investigated without reading anyone's data.

**Every state-changing request needs the XSRF token** — the `XSRF-TOKEN` cookie
echoed in the `X-XSRF-TOKEN` header.

**No personal data in any URL.** Opaque identifiers only. URLs reach access
logs, browser history and `Referer` headers.

---

## The shared privacy boundary

Both halves must uphold this. The full picture is [PRIVACY.md](PRIVACY.md).

### What each side is responsible for

|                             | Frontend                                                 | Backend                                                  |
| --------------------------- | -------------------------------------------------------- | -------------------------------------------------------- |
| **Must never hold**         | An API key, another user's data                          | A password in any recoverable form                       |
| **Must never log**          | Message content, email addresses                         | A credential, or a request body                          |
| **Must never put in a URL** | Anything personal                                        | Anything personal                                        |
| **Must always**             | Show the correlation ID on failure; mark stubs on screen | Check ownership in every query; use named SQL parameters |

### What actually crosses the network

| From    | To       | Carries              | Protected by                                 |
| ------- | -------- | -------------------- | -------------------------------------------- |
| Browser | Backend  | Plaintext messages   | TLS, XSRF, rate limits                       |
| Browser | Backend  | Raw audio            | TLS. **Goes no further**                     |
| Backend | Gemini   | Scrubbed prompt text | TLS, SSRF allowlist. **Leaves your control** |
| Backend | Database | Rows                 | TLS, one-address firewall                    |

**The row that matters is the third.** Everything else stays inside the
boundary. Prompts sent to Google do not, and on the free tier Google's terms
permit them to be used for product improvement and read by human reviewers.
This is why prompts are scrubbed, why the interface says so plainly, and why
enabling billing is the recommended fix before anyone else uses the
application.

**The row that surprises people is the second.** Audio reaches our backend and
stops there. It is transcribed by a model running on that machine and
discarded. See [ADR-008](docs/DECISIONS_PRIVACY.md).

---

## Deployment

Three tiers, three providers, in this order. Each depends on the one before, so
this order makes every failure diagnosable in isolation.

| Order | Tier                         | Guide                                                                                                                         |
| ----- | ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| 1     | **MySQL — cheapest path**    | [DEPLOY_MYSQL_HOSTINGER.md](docs/DEPLOY_MYSQL_HOSTINGER.md) — uses the database already included with your Hostinger plan. $0 |
| 1     | **MySQL — fallback**         | [DEPLOY_MYSQL_RDS.md](docs/DEPLOY_MYSQL_RDS.md) — free 12 months, then ~$14                                                   |
| —     | **The cross-cloud problem**  | [DEPLOY_CROSS_CLOUD.md](docs/DEPLOY_CROSS_CLOUD.md) — **only if you chose RDS.** Hostinger removes this problem entirely      |
| 2     | **Python on Fly.io**         | [DEPLOY_PYTHON_FLYIO.md](docs/DEPLOY_PYTHON_FLYIO.md)                                                                         |
| 3     | **Angular on Hostinger**     | [DEPLOY_ANGULAR_HOSTINGER.md](docs/DEPLOY_ANGULAR_HOSTINGER.md)                                                               |
| 4     | **Cloudflare**               | [CLOUDFLARE_WAF_PROMPT.md](CLOUDFLARE_WAF_PROMPT.md)                                                                          |
| —     | CORS, secrets, TLS, rollback | [DEPLOY_CROSS_CUTTING.md](docs/DEPLOY_CROSS_CUTTING.md)                                                                       |

**Nothing here has been deployed.** These are careful plans, not transcripts.
The container images in particular have not been built — Docker was not
installed where this was written.

### The two things most likely to go wrong

**1. The cookie domain.** The frontend and backend must sit under one parent
domain, or the browser will not let the frontend read the XSRF cookie, and
**every save will fail with a 403**:

```
frontend   https://app.yourdomain.com     ✓
backend    https://api.yourdomain.com     ✓  same parent
COOKIE_DOMAIN=.yourdomain.com

backend    https://something.fly.dev      ✗  nothing will save
```

Invisible locally, because both are `localhost`.

**2. Fly.io's egress address is not its ingress address.** The IP you allowlist
in AWS must be a **static egress IP** ($3.60/month), not the dedicated inbound
one. Get this wrong and the database connection works until a machine is
recreated, then silently stops.

### Verify between each step

- **After the database:** 13 tables and 13 procedures. On RDS, also confirm the
  application user cannot `DROP` — shared hosting cannot enforce that, which is
  a documented trade of the cheaper path.
- **After the backend:** `/health/ready` returns an **empty `warnings` list**.
  Do not continue while anything is in it.
- **After the frontend:** a deep link like `/settings` does not 404, and
  creating a campaign succeeds.
- **After Cloudflare:** the site still works and requests carry `CF-Ray`.

### The end-to-end check

Play one turn, then:

```bash
fly logs --no-tail | grep gemini_call_completed
```

You should see model, latency and token counts — **and no prompt or reply
content anywhere in the log.** That absence is the whole design working.

---

## Costs

[Full breakdown](docs/COSTS.md). Roughly **$14/month** in a new AWS account's
first year, **$34/month** afterwards.

About **$7** of that is the privacy design — mostly the larger machine needed
to transcribe audio locally rather than sending it to Google. Everything else
in the privacy design costs nothing but the decision to do it that way.

**What breaks first as you grow:** the Gemini free tier, at around ten daily
users. Then rate limiting, the moment you run two machines — Phase 1's limiter
counts per process, so two machines silently double every limit. Switch to the
database-backed limiter **before** scaling.

---

## Splitting into two repositories

`backend/` and `frontend/` are self-contained. To separate them:

```bash
cd backend && git init && git add . && git commit -m "Initial commit"
cd ../frontend && git init && git add . && git commit -m "Initial commit"
```

Then decide where the root documents live. The recommendation: **keep them in
the backend repository** and link from the frontend, because more of them
concern the backend. Whatever you choose, keep `SYSTEM_GUIDE.md` and
`PRIVACY.md` in exactly one place — duplicating them guarantees they diverge,
and a stale privacy document is worse than none.

---

## Roadmap

[Full version](docs/ROADMAP.md). In short:

1. **Connect the database** — everything depends on it.
2. **Real authentication** — required before anyone else uses it.
3. **Deploy** — get it in front of one friend.
4. **Streaming responses** — the biggest perceived-quality improvement.
5. Everything else, driven by what that friend says.

Deploying at step 3 rather than later is deliberate. Two weeks of one real
person using this will teach you more than any amount of further planning.

---

## Document index

**Root** — [README](README.md) · [RUNNING](RUNNING.md) ·
[ARCHITECTURE](ARCHITECTURE.md) · [PRIVACY](PRIVACY.md) ·
[CLOUDFLARE_WAF_PROMPT](CLOUDFLARE_WAF_PROMPT.md)

**docs/** — [Decisions](docs/ARCHITECTURE_DECISIONS.md)
([platform](docs/DECISIONS_PLATFORM.md),
[privacy](docs/DECISIONS_PRIVACY.md)) · deployment guides ·
[Costs](docs/COSTS.md) · [Roadmap](docs/ROADMAP.md) ·
[Glossary](docs/GLOSSARY.md)

**backend/docs/** — [Architecture](backend/docs/ARCHITECTURE.md) ·
[Conventions](backend/docs/CONVENTIONS.md) ·
[Database](backend/docs/DATABASE.md) ·
[Security](backend/docs/SECURITY.md) ·
[Observability](backend/docs/OBSERVABILITY.md) ·
[Testing](backend/docs/TESTING.md) · [Gemini](backend/docs/GEMINI.md) ·
[Glossary](backend/docs/GLOSSARY.md)

**frontend/docs/** — [Architecture](frontend/docs/ARCHITECTURE.md) ·
[Conventions](frontend/docs/CONVENTIONS.md) ·
[UI patterns](frontend/docs/UI_PATTERNS.md) ·
[Voice input](frontend/docs/VOICE_INPUT.md) · [Dice](frontend/docs/DICE.md) ·
[Testing](frontend/docs/TESTING.md) ·
[Glossary](frontend/docs/GLOSSARY.md)
