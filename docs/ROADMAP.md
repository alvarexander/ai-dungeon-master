# Roadmap

**Read this when** you have finished Phase 1 and want to know what comes next,
in what order, and why that order.

---

## Where things stand

**Phase 1 is complete and running locally.** The conversation with the Dungeon
Master works end to end against Google Gemini. Campaigns, characters, settings
and account deletion all work, with real encryption. 88 backend tests and 18
frontend tests pass.

**Two things are deliberately not real**, and the backend refuses to start in
production with either: authentication produces a placeholder session, and
storage is in memory. The database is fully designed with runnable migrations
and is connected to nothing.

---

## Phase 2 — make it real

The goal: something a friend can use without you being in the room.

### 2.1 Connect the database

**Why first:** everything else depends on data surviving a restart.

- Create the RDS instance and run the migrations
  ([guide](DEPLOY_MYSQL_RDS.md)).
- Write `SqlUserRepository` and its siblings against the existing interfaces.
  **Encryption happens at the same boundary**, so nothing above them changes.
- Swap `REPOSITORY_BACKEND=mysql`.

**Effort:** 2–3 days. **The interfaces exist; this is filling them in.**

### 2.2 Real authentication

**Why second:** pointless before data persists, and required before anyone else
touches it.

- Replace `issue_token` and `user_id_from_token` with signed, expiring tokens
  recorded in `user_sessions`, storing only a hash of each.
- Move the token from `localStorage` into an httpOnly cookie, so a cross-site
  scripting flaw cannot steal a session.
- Refresh-token rotation and revocation.
- Set `AUTH_MODE=real` — at which point the backend will start in production.
- **Remove every `<app-stub-notice>` from the auth screens in the same
  commit.** A stale warning trains people to ignore warnings.

**Effort:** 3–4 days.

### 2.3 Harden the database

- Move it off your laptop: [Hostinger](DEPLOY_MYSQL_HOSTINGER.md) is free if you
  already pay for hosting; [RDS](DEPLOY_MYSQL_RDS.md) is the alternative.
- Require TLS on the connection.
- Restrict access to the backend's address only.
- Confirm backups are running, and **restore one once** to prove they work. An
  untested backup is a hope, not a backup.

**Effort:** half a day.

### 2.4 Database-backed rate limiting

**Do this before running two machines**, not after. The in-memory limiter keeps
per-process tallies, so two machines silently double every limit — and the
symptom is nothing at all.

Point the limiter at `sp_rate_limit_hit`, which already exists.

**Effort:** half a day.

### 2.5 Email delivery

Unblocks password reset, email verification, and deletion confirmations.

Use a provider that supports a separate identity per environment, so a staging
mistake cannot email real users.

**Effort:** 2 days.

### 2.6 Deploy

Follow [SYSTEM_GUIDE.md](../SYSTEM_GUIDE.md) in order: database, backend,
frontend, Cloudflare. Verify between each.

**Effort:** a day if nothing surprises you; two if the cookie domain does.

---

## Phase 3 — make it good

Product work, once the foundation is real. Roughly in value order.

### 3.1 Streaming responses

Currently a player waits several seconds looking at three dots. Streaming shows
the narration appearing word by word, which feels dramatically faster even
though it takes the same time.

**Probably the single biggest perceived-quality improvement available.**
Requires server-sent events on the backend and incremental rendering on the
frontend.

### 3.2 Dice rolling in the interface

The Dungeon Master calls for checks; the player should be able to roll visibly
rather than typing a number. Animated, with the modifier applied and shown.

The `dice_rolls_visible` setting already exists for it.

### 3.3 Better memory of long campaigns

Only the last twenty messages travel with each turn, so after a few hours the
Dungeon Master forgets the innkeeper's name. Summarise older stretches into a
running "what has happened so far" and include that instead.

Genuinely improves long play, and reduces token cost per turn.

### 3.4 Multiple characters and party play

The schema already supports several characters per campaign. Sharing a campaign
between accounts is a larger piece of work — it touches the encryption model,
because two people's keys would need to open the same transcript. **Think that
through carefully before starting**; it is the one feature on this list that
could compromise the privacy design if done carelessly.

### 3.5 Campaign export

A player asks for their data and gets a readable file. Straightforward, and the
right thing to offer alongside a deletion that is genuinely irreversible.

### 3.6 Images

Scene illustrations via an image model. Expensive per image, and worth checking
the data-use terms of whichever model, for the same reasons as
[GEMINI.md](../backend/docs/GEMINI.md).

---

## Phase 4 — if it grows

Only relevant with real, sustained users.

- **Staging environment.** Once a mistake would affect other people.
- **Read replica**, if the database becomes a bottleneck. A long way off.
- **Redis for rate limiting**, faster than the database at high volume.
- **Multi-region.** Careful: every region far from AWS pays database latency on
  every query.
- **A moderation pathway.** You cannot read transcripts, by design. If
  moderation is ever needed, it must be user-reported and consent-based —
  design it deliberately rather than reaching for the break-glass role.

---

## Things deliberately not planned

Worth writing down so they are decisions rather than omissions.

**Server-Side Rendering.** Would require leaving Hostinger. No benefit for an
application behind a login. See
[the frontend architecture](../frontend/docs/ARCHITECTURE.md).

**A mobile app.** The web application works on a phone. A native app would
double the surface area for no capability this product needs.

**Self-hosting the language model.** The hardware costs vastly more than the
Gemini paid tier, and the quality would be worse.

**Searching transcripts.** Fundamentally incompatible with encrypting them. If
it is ever genuinely needed, the answer is a per-user index built in the
browser, not a change to the storage design.

**Social features.** Public campaigns, sharing, profiles. Each one is a new way
for personal data to escape, and the product does not need them.

---

## Suggested order

If you want a single sequence:

1. **Connect the database** — everything depends on it.
2. **Real authentication** — required before anyone else uses it.
3. **Deploy** — get it in front of one friend and learn what actually matters.
4. **Streaming responses** — the biggest perceived improvement.
5. **Everything else**, driven by what that friend says.

Deploying early, at step 3, is deliberate. Two weeks of one real person using
this will tell you more about what to build next than any amount of planning.

---

## Related documents

- [SYSTEM_GUIDE.md](../SYSTEM_GUIDE.md) — deployment.
- [Costs](COSTS.md) — what each stage costs.
- [Architecture decisions](ARCHITECTURE_DECISIONS.md) — what is expensive to
  reverse.
