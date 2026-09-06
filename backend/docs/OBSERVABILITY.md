# Observability

**Read this when** you are adding logging or analytics, or when somebody has
reported a problem and you need to work out what happened.

---

## Two things, with different jobs

| | Analytics | Logs |
|---|---|---|
| Answers | "How is the product doing?" | "What happened to this one request?" |
| Keyed by | The account | A correlation identifier |
| Retention | Long | 14 days |
| Free text | **None possible** | None written deliberately |

---

## Correlation identifiers: how you actually debug

Every request gets a random identifier. It is:

- returned in the `X-Correlation-ID` response header,
- stamped on every log line that request produces,
- **shown on the error screen in the interface.**

So when somebody reports a problem, you ask for the identifier and search the
logs for it. You then see the entire life of that one request — the route, the
status, the timings, the AI call, the exception.

**This is faster than the alternative**, which is finding their account and
reading rows. It also works when you do not know who they are, and it does not
involve reading somebody's conversation to fix a bug that has nothing to do
with what they wrote.

```bash
fly logs --no-tail | grep "3f1c9a7e-0b52-4d18-9a3e-77c0f1a2b8d4"
```

A client may supply its own identifier, so one user action can be traced across
several requests. It is accepted only if it is at most 64 characters and
alphanumeric-with-hyphens — an unfiltered value would let somebody inject
newlines and forge log lines.

---

## Logging

Structured JSON in production, human-readable locally. Configured in
`app/core/logging.py`.

### What is kept out

Fields whose names look like credentials — `password`, `api_key`,
`access_token`, `authorization`, `cookie`, `secret` — have their values replaced
with `<redacted>`. **Request bodies are never logged at all.**

Matching is on whole words, not substrings, and that detail matters. A naive
substring check on `token` also matches `tokens_in` — the count of tokens in an
AI prompt — and would quietly redact the numbers the whole cost story depends
on. It fails silently and looks like the filter working, which is the worst
kind of bug. There is a test for it.

The filter **fails closed**: if it raises, it emits a minimal record rather than
the original.

### The rule that replaces a bigger mechanism

**Log identifiers, not contents.**

A `user_id` tells you which account without putting anybody's words in a file
that gets copied to log aggregators and read by people. Every log call in this
codebase follows that rule.

Email addresses and message content are not stripped automatically. If you
deliberately log one, it will appear. That is a deliberate trade for
simplicity — you can log what you need while debugging without editing an
allowlist first — and it puts the responsibility on the person writing the log
line.

### The convention that matters most

```python
log.info("login_failed", user_id=str(user_id))    # right
log.info(f"login failed for {email}")              # wrong
```

The second bakes the address into the message itself, where nothing can inspect
it. It is also much harder to search, because every line is different.

### Errors

Full stack traces and exception types are logged. Those describe the code, not
the person. If Sentry or an equivalent is configured, run it with
`send_default_pii=False`.

---

## Gemini call observability

Logged for **every** call to the AI:

| Field | Why it matters |
|---|---|
| `model_id` | Which model answered, so a change in quality is traceable |
| `latency_ms` | The main signal that something is degrading |
| `tokens_in` / `tokens_out` | Free-tier consumption, visible in real time |
| `finish_reason` | `STOP` is normal; `SAFETY` and `max_tokens` are not |
| `safety_blocked` | A spike means the Dungeon Master prompt needs attention |
| `error_code` | The provider's code, e.g. `RESOURCE_EXHAUSTED`. Never a message body — provider messages sometimes quote the request back |
| `retry_count` | Rising values mean the upstream is struggling |

**Not the prompt and not the response.** Those are the player's words, and they
are not needed to diagnose latency, quota or safety problems — which is what
almost every AI issue turns out to be.

A worked example. A player says "the Dungeon Master repeated itself three
times." You ask for the correlation identifier and find the turn had
`finish_reason: max_tokens` and 3,900 input tokens — the history window was
full. Diagnosed from metrics alone, without reading their campaign.

---

## Analytics

Counts and categories, in `app/services/analytics.py` and the
`analytics_events` table.

**There is no free-text column.** Every field is an enumerated value, a number,
a boolean or a timestamp. A careless change later cannot start recording what
players typed, because there is nowhere for it to land.

Unknown event names raise `AnalyticsRejected` at write time rather than being
dropped silently, so the mistake shows up during development instead of
becoming a permanent gap in the data.

### What is collected

- Sessions started and ended; session duration, in buckets
- Turns taken; voice versus typed input
- Campaigns and characters created
- Errors by category; how often the AI quota runs out
- Signups and successful sign-ins
- Country, from the edge network's `CF-IPCountry` header

**Durations are bucketed** (`lt_1m`, `1_5m`, `5_15m`…) rather than exact. An
exact session length of 1,847 seconds is close to unique and can act as a
fingerprint linking records; "30 to 60 minutes" cannot.

**Geography is country only.** Taken from a header the edge network adds, so
the server never inspects or stores an IP address to work it out. Never city — a
city plus a timestamp plus a session length is close to identifying.

### After an account is deleted

Events survive with their `user_id` set to `NULL`. The totals stay correct; the
person disappears from them. Business metrics should not drop retroactively
every time somebody closes their account.

---

## What you can and cannot answer

**Instantly, with no user involvement:**

- How many people played yesterday, this week, this month
- Which classes and tones are popular
- Voice versus typed usage
- Error rates by category; how often the AI quota is exhausted
- AI latency, token consumption, safety-block rate
- Whether a deployment made anything worse

**With the correlation identifier from the user:**

- Why one specific request failed
- What the AI did on one particular turn
- Which validation rule rejected a submission

**By looking in the database:**

- What a specific user wrote, if you genuinely need to. It is readable — the
  protection is that very few people can reach the database, not that the
  contents are scrambled. Do it because you need to, not because it is easy.

---

## Related documents

- [SECURITY.md](SECURITY.md) — the protections around the data.
- [DATABASE.md](DATABASE.md) — the analytics table.
- [PRIVACY.md](../../PRIVACY.md) — the overall posture.
