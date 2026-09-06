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

| I want to…                             | Read                                             |
| -------------------------------------- | ------------------------------------------------ |
| **Run it on my machine**               | **[RUNNING.md](RUNNING.md)**                     |
| Understand how it works, with diagrams | [ARCHITECTURE.md](ARCHITECTURE.md)               |
| Know what happens to my users' data    | [PRIVACY.md](PRIVACY.md)                         |
| Get a Google Gemini key                | [backend/docs/GEMINI.md](backend/docs/GEMINI.md) |
| Deploy it to real servers              | [SYSTEM_GUIDE.md](SYSTEM_GUIDE.md)               |
| Look up a word                         | [docs/GLOSSARY.md](docs/GLOSSARY.md)             |

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

| Tier     | Technology                                             | Runs on                                    |
| -------- | ------------------------------------------------------ | ------------------------------------------ |
| Frontend | Angular 22, standalone components, signals, **no SSR** | Hostinger (static files)                   |
| Backend  | Python 3.12, FastAPI                                   | Fly.io (container)                         |
| Database | MySQL                                                  | Hostinger (free with your plan) or AWS RDS |

Today all three run on your laptop. Keeping them separate from the start forces
two things to be right that are painful to retrofit: the frontend must build to
plain files with no server process, and the two halves must cope with being on
different web addresses.

---

## What makes this project unusual

Most of the effort here went somewhere that is not visible on screen.

**Passwords are hashed with Argon2id and never stored.** Not encrypted —
hashed, one way, unrecoverable by anybody including us. The distinction is
[written down](docs/DECISIONS_PRIVACY.md), because it is the one newcomers most
often get wrong.

**Voice never reaches Google.** The browser's built-in speech recognition
streams raw microphone audio to Google's servers, so it is not used.
Transcription happens on our own server instead. That costs about four dollars
a month, and the reasoning is in [ADR-008](docs/DECISIONS_PRIVACY.md).

**The dice are the real solids.** A d20 is an icosahedron, a d10 is a
pentagonal trapezohedron with kite-shaped faces, and each face carries its
number and turns to face you when the die stops. The shapes are computed from
the corners of each solid rather than drawn by eye, which is why they are
correct and why they can be tested. A dice roller that shows the wrong shape is
the sort of detail a player notices immediately.

**Analytics cannot record what people typed.** Not by convention — there is
physically no free-text column in the analytics table, so a careless change
later cannot start collecting one.

**Every query includes the owner.** Ownership is part of the `WHERE` clause
rather than checked afterwards, so one account cannot reach another's rows by
guessing an identifier. Every SQL query uses named parameters, which makes
injection impossible rather than unlikely.

**The application refuses to start** if it is marked as production while any
development shortcut remains — stubbed authentication, insecure cookies, a
database without TLS.

**And a deliberate non-feature:** there is no application-layer encryption of
personal data. That was considered, built, and then removed on purpose —
[ADR-002](docs/DECISIONS_PRIVACY.md) explains why, and is honest about what it
costs.

The reasoning for each of these is in
[docs/ARCHITECTURE_DECISIONS.md](docs/ARCHITECTURE_DECISIONS.md), together with
what each would cost to reverse.

---

## What is honestly not finished

Stated plainly, because a project that hides its gaps wastes the next person's
afternoon:

- **Authentication.** Registration, Argon2id password hashing and the encrypted
  email lookup are all real. The _session token_ is a placeholder the backend
  does not verify. Every affected screen says so on screen, and the backend
  will not start in production this way.
- **The database.** MySQL works — set `REPOSITORY_BACKEND=mysql` and follow
  [docs/LOCAL_MYSQL.md](docs/LOCAL_MYSQL.md). The default is an in-memory store
  that needs nothing installed and loses everything on restart.
- **Password reset and changing your email.** Both need email delivery.
- **Deployment.** Documented in full; not performed.

---

## Tests

```bash
cd backend  && uv run pytest    # 90
cd frontend && npm test         # 52
```

The frontend suite runs entirely without a browser, including the tests for the
**shapes of the dice** — that a d20 has twenty faces, that each is a triangle,
that they are all the same size, and that rolling a 17 shows the 17. That is
possible only because the geometry was written as plain functions before it was
turned into styles. It is also how a real bug in those shapes was caught before
it shipped.

The backend suite runs **real** Argon2id rather than a mock. It also verifies
that credentials never reach a log, that the SSRF guard refuses internal
addresses, that login failures are indistinguishable whether or not an account
exists, that validation errors never echo the submitted value, and that one
account cannot read another's campaigns.

---

## Credits and licence

Built as a learning project. Dungeons & Dragons is a trademark of Wizards of
the Coast; this project is unaffiliated and implements only the rules concepts
needed to play.

No licence is set. Add one before publishing.
