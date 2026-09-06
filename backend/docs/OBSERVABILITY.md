# Observability

**Read this when** you are adding logging or analytics, or when someone has
reported a problem and you need to investigate it without reading their data.

---

## Two planes that never meet

| | Analytics | Debug telemetry |
|---|---|---|
| Answers | "How is the product doing?" | "What happened to this one request?" |
| Identified by | A pseudonym unrelated to the account | A correlation identifier |
| Retention | Aggregates indefinitely, raw events 90 days | 14 days, then hard delete |
| Free text | **None exists anywhere** | None permitted |
| Joins to identity | Structurally impossible | Opaque user id only |

Keeping them apart is what lets the first be retained for years without
accumulating a history of anybody.

---

## Plane 1 — analytics

### The pseudonym

Every user has an `analytics_id`: a random UUID with no mathematical
relationship to their `user_id`. The link between them lives in exactly one
place, `user_analytics_map`, and is **encrypted under the user's own key**.

That last detail is the point. Crypto-shredding a user destroys the link
automatically, even if the mapping row somehow survives in an old backup. Their
events remain and keep counting toward totals, but nothing on earth can
attribute them to a person again.

**So deletion is complete and the business metrics survive.** Both, not a
trade.

### The allowlist is a schema, not a promise

`analytics_events` accepts only declared fields, and every one is an enum, a
boolean, a number or a timestamp. **There is no free-text column anywhere in
the analytics schema.**

This is a mechanism rather than a rule someone must remember. A careless change
cannot smuggle a player's message into analytics because there is physically
nowhere for it to land. Two layers enforce it:

- `AnalyticsService.record` raises `AnalyticsRejected` on an undeclared event,
  feature or category — loudly, at write time, not silently dropped.
- The application role has **no direct INSERT** on `analytics_events`. The only
  way in is `sp_analytics_record`, whose parameters are all enums, so MySQL
  itself rejects an unrecognised value in strict mode.

Adding an event means changing `ALLOWED_EVENTS` *and* the SQL `ENUM`, in the
same commit — which is exactly the right moment to ask whether the new event
reveals anything about a person.

### The counters, designed up front

Aggregates cannot be backfilled after users are crypto-shredded — the data is
genuinely gone. So they are defined now, and the bias is deliberately toward
over-collecting *aggregates* while under-collecting *records*:

- session count, session duration in buckets, turns per session
- retention cohort by signup week
- feature usage: voice versus typed, character sheet, campaign list
- error rates by category
- quota exhaustions, so you can see the free tier biting

`sp_analytics_rollup_day` computes these nightly. They outlive the raw events
they came from, which is what makes a 90-day raw retention survivable.

### Geography

Country only, and never by keeping the address. In production Cloudflare adds a
`CF-IPCountry` header, so the country arrives already computed and this server
never inspects, stores, or looks up an IP address to obtain it.

Never city. A city plus a timestamp plus a session length is close to
identifying.

### Durations are bucketed

An exact session length of 1,847 seconds is nearly unique and can act as a
fingerprint linking records. `lt_1m`, `1_5m`, `5_15m`, `15_30m`, `30_60m`,
`gt_60m` cannot.

---

## Plane 2 — debug telemetry

### Correlation identifiers

Every request gets one. It is:

- returned in the `X-Correlation-ID` response header,
- stamped on every log line for that request,
- displayed on the error screen in the interface.

**This is the primary debugging workflow, not a fallback.** A user reports a
problem, you ask for the identifier, you search the logs, and you see the
entire life of that one request — without touching their data.

A supplied identifier is accepted only if it is at most 64 characters and
alphanumeric-with-hyphens. An unfiltered value would let an attacker inject
newlines and forge log lines, or attribute their trace to somebody else.

### Structured logs, and the allowlist

Logs are JSON in production. Every entry passes through `redaction_processor`
before being written.

**It is an allowlist, and that choice is the whole point.** A blocklist names
the fields to hide — password, email, token — and fails the first time somebody
adds `recovery_address`. It protects only against mistakes you already thought
of. An allowlist censors by default: a field invented tomorrow is protected
today, without anyone remembering.

Anything not in `LOGGABLE_FIELDS` is replaced with a description of its type
and length: `<str:len=24>`, `<dict:keys=3>`, `<int>`. Enough to debug "it was
empty when I expected 40 characters" and nothing about the content.

**Numbers are censored by type, not value**, because an undeclared number could
be a date of birth.

**It fails closed.** If the filter itself raises, it emits a minimal safe record
rather than the original. A filter that failed open would be worse than none,
because it would create confidence that is not warranted.

**The one hole it cannot close** is the `event` field, which is the message
itself. The rule is a convention: event names are fixed strings, never
f-strings. `log.info(f"login failed for {email}")` puts the address straight
past the filter. Variable content goes in named fields.

### What is logged about a user

`user_id` — a random UUID that reveals nothing. Never a username, never an
email, never a decrypted field.

### Errors

Full stack traces, exception types and application state are fair game — none
of that identifies a person. If Sentry or an equivalent is configured, it must
run with `send_default_pii=False` and the same redaction filter applied before
transmission.

### Retention

14 days, then hard delete. Long enough to investigate a report that arrives a
week late; short enough that a log archive does not become a shadow database.

---

## Gemini call observability

Logged for **every** call:

| Field | Why |
|---|---|
| `model_id` | Which model answered, so a change in quality is traceable |
| `latency_ms` | The main signal that something is degrading |
| `tokens_in` / `tokens_out` | Free-tier consumption, visible in real time |
| `finish_reason` | `STOP` is normal; `SAFETY` and `max_tokens` are not |
| `safety_blocked` | A spike means the DM prompt needs attention |
| `error_code` | The provider's code, e.g. `RESOURCE_EXHAUSTED`. Never a message body — provider messages sometimes quote the request back |
| `retry_count` | Rising values mean the upstream is struggling |
| `estimated_cost_micros` | Zero on the free tier; ready for when it is not |

**Never the prompt and never the response.** Those are the player's words.

Phase 2 writes the same fields to `gemini_calls`, a table that deliberately has
no content columns at all — so there is nowhere for content to be added by
accident.

---

## The opt-in debug capture

Some faults genuinely cannot be diagnosed without seeing the prompt. The escape
hatch is the player's to open, not ours.

`POST /api/v1/chat/sessions/{id}/debug-capture` with `{"enabled": true}`:

- stores the exact prompt and response **encrypted under the player's own key**,
- for at most **48 hours**, enforced in code rather than trusted to the caller,
- readable only through the audited support flow below,
- surfaced in the interface as "help us debug this session", because that is
  exactly what it is.

Crypto-shredding an account deletes its captures immediately rather than
waiting for expiry.

---

## Supervised access to plaintext

**Ad-hoc `SELECT` against production is not a debugging tool in this design.**
Your own administrator role cannot call KMS `Decrypt` on the user data key —
only the application role can — so the rows would be unreadable anyway.

When plaintext genuinely is needed:

1. A support endpoint takes an explicit **reason string**, a target user id,
   and a **time-boxed grant** (default one hour).
2. `sp_support_grant_open` writes the grant and the user-visible disclosure **in
   one transaction**. They cannot come apart: if the audit write fails, no
   grant is created.
3. The reason is encrypted under a **separate audit key**, not the user's. If
   it used the user's key, crypto-shredding them would erase the record of who
   looked at their data — destroying exactly the evidence an audit needs.
4. The grants table is **append-only**: the application role has INSERT and
   SELECT, never UPDATE or DELETE. Code that could erase its own audit trail is
   not an audit trail.
5. A CloudTrail alert fires on every KMS `Decrypt` by the break-glass role.
6. **The user sees it** in their own account activity, with the reason given.

---

## What this costs you operationally

Being concrete, because this is the bill for the whole design.

**Answerable instantly, no user involvement:**

- How many people played yesterday, this week, this month
- Retention by signup cohort
- Which classes and tones are popular
- Voice versus typed usage
- Error rates by category; how often the AI quota is exhausted
- AI latency, token consumption, safety-block rate
- Whether a specific deployment made anything worse

**Answerable, but you need the correlation identifier from the user:**

- Why one specific request failed
- What the AI did on one particular turn
- Which validation rule rejected a submission

This is the trade. You cannot search logs by email address to find someone's
problem. You ask for the identifier the error screen showed them.

**Not answerable without their explicit, recorded consent:**

- What a user actually typed
- Why the Dungeon Master produced a strange reply for a particular player
- Anything requiring you to read a transcript

For these, the player switches on debug capture, or you open an audited grant
and they are told.

**A worked example.** A player says "the Dungeon Master repeated itself three
times." You cannot read their session. You ask for the identifier and find the
turn had `finish_reason: max_tokens` and 3,900 input tokens — the history
window was full. Diagnosed from metrics alone. If that had not been enough, you
would ask them to turn on debug capture and play the turn again.

**What it buys.** A database leak exposes usernames and timestamps. That is the
entire breach. No email addresses to sell, no transcripts to publish, no
disclosure describing what was in them.

---

## Related documents

- [SECURITY.md](SECURITY.md) — encryption and key custody.
- [DATABASE.md](DATABASE.md) — the analytics tables and their absent joins.
- [Privacy decisions](../../docs/DECISIONS_PRIVACY.md) — why two planes.
