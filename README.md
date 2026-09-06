# AI Dungeon Master

A web application that plays Dungeon Master, for people who want to play
Dungeons & Dragons and do not have a human running the game. You describe what
your character does — by typing or by speaking — and the Dungeon Master
narrates what happens, plays every character in the world, and handles the
rules.

**Phase 1 status: running locally, end to end.** The conversation with the
Dungeon Master genuinely works, backed by Google Gemini. Campaigns, characters
and settings all work. Sign-in is deliberately not implemented yet, and the
database is designed but not connected.

---

## Start here

| I want to… | Read |
|---|---|
| **Run it on my machine** | **[RUNNING.md](RUNNING.md)** |
| Understand how it works, with diagrams | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Know what happens to my users' data | [PRIVACY.md](PRIVACY.md) |
| Get a Google Gemini key | [backend/docs/GEMINI.md](backend/docs/GEMINI.md) |
| Deploy it to real servers | [SYSTEM_GUIDE.md](SYSTEM_GUIDE.md) |
| Look up a word | [docs/GLOSSARY.md](docs/GLOSSARY.md) |

**If you are new to this project, [RUNNING.md](RUNNING.md) is the file you
want.** It assumes no prior experience and explains what every command does.

---

## What is here

```
ai-dungeon-master/
├── RUNNING.md            how to start it, step by step
├── ARCHITECTURE.md       how it all fits together, with diagrams
├── PRIVACY.md            threat model, data classification, what a breach exposes
├── SYSTEM_GUIDE.md       deployment, costs, roadmap
├── CLOUDFLARE_WAF_PROMPT.md   a self-contained prompt for configuring the firewall
├── docs/                 decisions, deployment guides, costs, glossary
├── backend/              the Python service  (its own AGENTS.md and docs/)
└── frontend/             the Angular app     (its own AGENTS.md and docs/)
```

`backend/` and `frontend/` are self-contained and can be split into separate
Git repositories at any point — see [SYSTEM_GUIDE.md](SYSTEM_GUIDE.md).

---

## The three tiers

The application is three separate pieces, deliberately, which in production run
with three different providers:

| Tier | Technology | Runs on |
|---|---|---|
| Frontend | Angular 22, standalone components, signals, **no SSR** | Hostinger (static files) |
| Backend | Python 3.12, FastAPI | Fly.io (container) |
| Database | MySQL | AWS RDS |

Today all three run on your laptop, with the database replaced by an in-memory
store. Keeping them separate from the start forces three things to be right
that are painful to retrofit: the frontend must build to plain files, the two
halves must cope with being on different web addresses, and the backend must
reach a database in another company's network.

---

## What makes this project unusual

Most of the effort here went somewhere that is not visible on screen.

**Everything personal is encrypted with a key belonging to one user.** Email
addresses, campaign titles, character names, and every message in every
conversation. Somebody who stole a complete copy of the database would find
usernames and timestamps, and nothing else they could read.

**Deleting an account destroys the key rather than the data.** Which makes it
effective in backups nobody can reach into and edit — and genuinely
irreversible, including by us.

**Logs censor by default.** A field not explicitly declared safe to log is
replaced by a description of its type and length. A field invented tomorrow is
protected today.

**Voice never reaches Google.** The browser's built-in speech recognition
streams raw microphone audio to Google's servers, so it is not used.
Transcription happens on our own server instead. That costs about five dollars
a month, and the reasoning is written down in
[ADR-008](docs/DECISIONS_PRIVACY.md).

**Abuse prevention needs no plaintext.** Rate limiting counts fingerprints of
addresses, using a salt that changes daily and is never stored. Privacy and
security do not trade off against each other.

**The application refuses to start** if it is marked as production while any
development shortcut remains — a written-down encryption key, stubbed
authentication, logging with redaction switched off.

The reasoning for each of these is in
[docs/ARCHITECTURE_DECISIONS.md](docs/ARCHITECTURE_DECISIONS.md), together with
what each would cost to reverse.

---

## What is honestly not finished

Stated plainly, because a project that hides its gaps wastes the next person's
afternoon:

- **Authentication.** Registration, Argon2id password hashing and the encrypted
  email lookup are all real. The *session token* is a placeholder the backend
  does not verify. Every affected screen says so on screen, and the backend
  will not start in production this way.
- **The database.** Fully designed, with runnable migrations and stored
  procedures, and connected to nothing. Phase 1 keeps everything in memory, so
  a restart loses it all.
- **Password reset and changing your email.** Both need email delivery.
- **Deployment.** Documented in full; not performed.

---

## Tests

```bash
cd backend  && uv run pytest    # 88
cd frontend && npm test         # 18
```

The backend suite runs the **real** encryption rather than a mock, because a
mock of encryption proves nothing. It verifies that ciphertext does not contain
the plaintext, that a value cannot be moved between users or columns, that
tampering is detected, that a deleted user's data is unreadable, and that the
log filter censors a field nobody has declared.

---

## Credits and licence

Built as a learning project. Dungeons & Dragons is a trademark of Wizards of
the Coast; this project is unaffiliated and implements only the rules concepts
needed to play.

No licence is set. Add one before publishing.
