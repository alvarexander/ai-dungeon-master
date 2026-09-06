# Architecture Decisions — Index

**Read this when** you need the reasoning behind a structural choice, or when
you are about to change something significant and want to know what it will
break.

The decisions live in two files, split only because one would be long:

- **[Platform decisions](DECISIONS_PLATFORM.md)** — the web framework, code
  layering, rendering mode, storage backends, and joining two clouds.
- **[Security decisions](DECISIONS_PRIVACY.md)** — password storage, what the
  database does and does not protect, analytics, deletion, rate limiting, and
  speech-to-text.

If you change a decision, update its entry in the same commit.

---

## All decisions at a glance

| # | Decision | Where |
|---|---|---|
| ADR-001 | Python web framework: FastAPI | [Platform](DECISIONS_PLATFORM.md) |
| ADR-002 | Conventional security, not application-layer encryption | [Security](DECISIONS_PRIVACY.md) |
| ADR-003 | Passwords are hashed with Argon2id, never encrypted | [Security](DECISIONS_PRIVACY.md) |
| ADR-004 | Analytics has no free-text column | [Security](DECISIONS_PRIVACY.md) |
| ADR-005 | Deletion removes the data | [Security](DECISIONS_PRIVACY.md) |
| ADR-006 | Correlation identifiers for debugging | [Security](DECISIONS_PRIVACY.md) |
| ADR-007 | Rate limiting | [Security](DECISIONS_PRIVACY.md) |
| ADR-008 | Server-side speech-to-text, not the browser's Web Speech API | [Security](DECISIONS_PRIVACY.md) |
| ADR-009 | Server-Side Rendering stays off | [Platform](DECISIONS_PLATFORM.md) |
| ADR-010 | Layering: routes → services → repositories | [Platform](DECISIONS_PLATFORM.md) |
| ADR-011 | Cross-cloud database access: public endpoint, locked to one address | [Platform](DECISIONS_PLATFORM.md) |
| ADR-013 | Two storage backends behind one interface | [Platform](DECISIONS_PLATFORM.md) |
| ADR-014 | Plain SQL, not an ORM | [Platform](DECISIONS_PLATFORM.md) |

---

## The three worth reading first

1. **[ADR-002 — conventional security, not encryption](DECISIONS_PRIVACY.md)**
   — what the database does and does not protect, and why an earlier
   encryption design was deliberately removed.
2. **[ADR-003 — Argon2id passwords](DECISIONS_PRIVACY.md)** — the one control
   kept at full strength, and why hashing is not encryption.
3. **[ADR-008 — local speech-to-text](DECISIONS_PRIVACY.md)** — the one place
   this project spends real money on a data-handling choice, and the reasoning.
