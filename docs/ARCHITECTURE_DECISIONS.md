# Architecture Decisions — Index

**Read this when** you need to find the reasoning behind a structural choice, or
when you are about to change something significant and want to know what it will
break.

Every decision in this project was made once, deliberately, and written down.
The decisions live in two files, split only because a single file would be too
long to read comfortably:

- **[Platform decisions](DECISIONS_PLATFORM.md)** — the web framework, code
  layering, rendering mode, and how three clouds are joined together.
- **[Privacy decisions](DECISIONS_PRIVACY.md)** — encryption, login lookup,
  password storage, deletion, telemetry, and speech-to-text.

If you change a decision, update its entry in the same commit.

---

## All decisions at a glance

| # | Decision | Where |
|---|---|---|
| ADR-001 | Python web framework: FastAPI | [Platform](DECISIONS_PLATFORM.md#adr-001-python-web-framework-fastapi) |
| ADR-002 | Encryption strategy: application-layer envelope encryption | [Privacy](DECISIONS_PRIVACY.md#adr-002-encryption-strategy-application-layer-envelope-encryption) |
| ADR-003 | Email lookup: keyed blind index | [Privacy](DECISIONS_PRIVACY.md#adr-003-email-lookup-keyed-blind-index) |
| ADR-004 | Passwords are hashed, never encrypted | [Privacy](DECISIONS_PRIVACY.md#adr-004-passwords-are-hashed-never-encrypted) |
| ADR-005 | Deletion by crypto-shredding | [Privacy](DECISIONS_PRIVACY.md#adr-005-deletion-by-crypto-shredding) |
| ADR-006 | Two separate telemetry planes | [Privacy](DECISIONS_PRIVACY.md#adr-006-two-separate-telemetry-planes) |
| ADR-007 | Rate limiting on hashed identifiers | [Privacy](DECISIONS_PRIVACY.md#adr-007-rate-limiting-on-hashed-identifiers) |
| ADR-008 | Server-side speech-to-text, not the browser's Web Speech API | [Privacy](DECISIONS_PRIVACY.md#adr-008-server-side-speech-to-text-not-the-browser-s-web-speech-api) |
| ADR-009 | Server-Side Rendering stays off | [Platform](DECISIONS_PLATFORM.md#adr-009-server-side-rendering-stays-off) |
| ADR-010 | Layering: routes → services → repositories | [Platform](DECISIONS_PLATFORM.md#adr-010-layering-routes-services-repositories) |
| ADR-011 | Cross-cloud database access: public endpoint, locked to one address | [Platform](DECISIONS_PLATFORM.md#adr-011-cross-cloud-database-access-public-endpoint-locked-to-one-address) |
| ADR-012 | AWS credentials on Fly.io: OIDC federation, no stored keys | [Platform](DECISIONS_PLATFORM.md#adr-012-aws-credentials-on-fly-io-oidc-federation-no-stored-keys) |
| ADR-013 | Phase 1 runs with no database | [Platform](DECISIONS_PLATFORM.md#adr-013-phase-1-runs-with-no-database) |

---

## The four that are expensive to reverse

If you only read four entries, read these. Changing any of them later means
rewriting stored data, not just code.

1. **[ADR-002 — envelope encryption](DECISIONS_PRIVACY.md)** — every piece of
   personal data is locked with a key unique to that user. Everything else in
   the privacy design rests on this.
2. **[ADR-005 — crypto-shredding](DECISIONS_PRIVACY.md)** — account deletion
   destroys the key, not the data, which is how deletion reaches backups you
   cannot edit.
3. **[ADR-006 — two telemetry planes](DECISIONS_PRIVACY.md)** — aggregate
   counters cannot be backfilled after users are deleted, so they must be
   designed before you have users, not after.
4. **[ADR-001 — FastAPI](DECISIONS_PLATFORM.md)** — the entire backend is
   written in its idioms.
