# Database — Operations

**Read this when** you need to query the database, call a stored procedure,
add a migration, or set up database permissions. For what the tables contain
and how each column is protected, read [DATABASE.md](DATABASE.md) first.

---

## The main access patterns

These are the queries the application actually runs. Each one is shown with
the thing worth noticing about it — usually that no plaintext personal data
appears anywhere in the statement or the result.

### 1. Log a user in

The application computes the blind index fingerprint first, in Python, using a
key the database has never seen:

```sql
CALL sp_user_find_by_email_bidx(UNHEX('9f2c...32bytes'));
```

Notice what went in: 32 bytes of fingerprint. Notice what comes back:
ciphertext and a wrapped key. The database matched an email address without an
email address ever existing inside it.

### 2. Check a rate limit

```sql
CALL sp_rate_limit_hit(UNHEX('a71b...32bytes'), 'login', 900, 5);
```

Returns `allowed`, `hit_count`, `retry_after_secs`. The first argument is an
HMAC of the caller's IP address. **This is the demonstration that abuse
prevention needs no plaintext**: the entire login-throttling path is one call
taking a digest and returning a number.

### 3. List a user's campaigns

```sql
SELECT campaign_id, title_ct, premise_ct, ruleset, tone, status,
       dek_key_version, updated_at
  FROM campaigns
 WHERE user_id = UNHEX('...') AND status = 'active'
 ORDER BY updated_at DESC
 LIMIT 50;
```

Sorting is by `updated_at`, a timestamp. You cannot sort campaigns
alphabetically by title in the database, because the database cannot read the
titles — sorting by name happens in Python after decryption. That is a real
cost of the design, and it is why the list is capped at 50.

### 4. Load a conversation page

```sql
CALL sp_session_transcript_page(UNHEX('...'), 0, 50);
```

Paging uses `seq`, an integer. No `LIKE` search over message content is
possible, ever — see "What you cannot do" below.

### 5. Append a message

```sql
CALL sp_message_append(
  UNHEX('...'),        -- message_id
  UNHEX('...'),        -- game_session_id
  UNHEX('...'),        -- user_id
  'player',
  0x8f21...,           -- content_ct, encrypted before it left Python
  'voice', 42, 1
);
```

### 6. Record an analytics event

```sql
CALL sp_analytics_record(
  UNHEX('...'),   -- analytics_id, not user_id
  'turn_taken', 'GB', NULL, 7, 'voice_input', NULL, 1
);
```

Every argument is an enum value, a country code, or a number. There is no
parameter that accepts free text, so nothing a player typed can reach here.

### 7. Delete an account

```sql
CALL sp_user_crypto_shred(UNHEX('...'));
```

One call. It destroys the key and severs the analytics link. It does not touch
the transcripts, because it does not need to.

### 8. Answer "how is the product doing?"

```sql
SELECT day, metric, dimension, value
  FROM analytics_daily_aggregates
 WHERE day BETWEEN '2026-08-01' AND '2026-08-31'
   AND metric IN ('active_users','sessions','turns','voice_turns')
 ORDER BY day, metric;
```

This query touches no personal data and needs no key. It also keeps working
after every user in it has deleted their account.

### 9. Watch the AI for trouble

```sql
SELECT DATE(created_at) AS day,
       model_id,
       COUNT(*) AS calls,
       AVG(latency_ms) AS avg_ms,
       SUM(finish_reason = 'safety') AS safety_blocks,
       SUM(error_code = 'RESOURCE_EXHAUSTED') AS quota_hits
  FROM gemini_calls
 WHERE created_at >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL 7 DAY)
 GROUP BY day, model_id
 ORDER BY day DESC;
```

`quota_hits` is the number that tells you the Gemini free tier is squeezing you.

### 10. Trace one user's bug report

The user gives you a correlation identifier from the error screen:

```sql
SELECT call_id, model_id, latency_ms, tokens_in, tokens_out,
       finish_reason, error_code, retry_count, created_at
  FROM gemini_calls
 WHERE correlation_id = UNHEX('...');
```

This is the intended debugging workflow. Not `SELECT * FROM users`.

---

## What you cannot do, and what to do instead

Being honest about the losses:

| You cannot | Because | Do this instead |
|---|---|---|
| Search messages for a word | Content is ciphertext | Not supported. If you ever need it, the answer is a per-user searchable index built client-side, not a database change |
| Sort campaigns by title in SQL | Titles are ciphertext | Fetch, decrypt, sort in Python. Capped page sizes keep this cheap |
| `SELECT` a user by email | No email column exists | Compute the blind index, then query by fingerprint |
| Find "all users in London" | IP addresses are hashed, geography is country-only and discarded | Use `analytics_events.country_code` for aggregate country counts |
| Read a transcript to debug a fault | Transcripts are encrypted, and you hold no user keys as an administrator | Ask the user for their correlation ID, or use the audited support flow with their knowledge |

---

## Stored procedure index

Every procedure is defined in
[`migrations/0002_stored_procedures.sql`](../migrations/0002_stored_procedures.sql).
None of them accepts or returns plaintext personal data.

| Procedure | Purpose | Plaintext personal data involved? |
|---|---|---|
| `sp_rate_limit_hit` | Count a request against a limit | No — digest in, number out |
| `sp_rate_limit_prune` | Housekeeping | No |
| `sp_user_find_by_email_bidx` | Login lookup | No — fingerprint in, ciphertext out |
| `sp_user_find_by_username` | Profile lookup | No — username is non-personal |
| `sp_user_crypto_shred` | Account deletion | No — opaque identifier only |
| `sp_session_transcript_page` | Read conversation | No — returns ciphertext |
| `sp_message_append` | Write a message | No — receives ciphertext |
| `sp_analytics_record` | Record an event | No — enums and numbers only |
| `sp_analytics_rollup_day` | Nightly aggregation | No |
| `sp_analytics_purge_raw` | 90-day retention | No |
| `sp_debug_captures_expire` | 48-hour retention | No |
| `sp_support_grant_open` | Open an audited access window | No — receives pre-encrypted reason |
| `sp_support_grant_check` | Validate a grant | No |

---

## Migrations

### What a migration is and why you cannot skip one

The database starts empty. A migration is a numbered file of instructions that
changes its structure. They run in order, once each, and are never edited after
they have run anywhere real.

If you skip one, the application will expect a column that does not exist and
will fail on the first request that touches it — usually with an error like
`Unknown column 'users.dek_key_version' in 'field list'`. If you edit one that
has already run, your laptop and the server end up with silently different
schemas, which is considerably worse than an error.

### The recommended tool: Alembic, with hand-written migrations

**Alembic** is the migration runner from the SQLAlchemy project. Recommended,
with one important restriction: **do not use its autogenerate feature.**

Autogenerate compares your Python models to the live database and writes the
difference for you. It is convenient and wrong for this project, for two
reasons. It cannot see stored procedures at all, so it would propose dropping
them or silently ignore them. And it does not understand that a `VARBINARY`
column is a deliberate encrypted field — given a Python model that says "email
is a string", it will helpfully offer to convert your ciphertext column to
`VARCHAR`, which would corrupt every row.

So: Alembic runs the migrations, you write them by hand. The `migrations/`
folder holds plain `.sql` files, and
[`scripts/migrate.py`](../scripts/migrate.py) applies them in order, recording
each in `schema_migrations` with a checksum so an edited file is caught.

### The workflow for changing the schema

1. Write a new numbered file, e.g. `0004_add_campaign_notes.sql`. Never edit an
   existing one.
2. Classify every new column in its `COMMENT`. Personal data is `ENCRYPTED`.
   If you are unsure whether something is personal, it is.
3. Update [DATABASE.md](DATABASE.md) **in the same commit**. This is a hard rule
   from the project brief, not a nicety.
4. Run it locally, confirm the application still starts.
5. Run it against staging, then production.

### Expand and contract, for changes that cannot break

Renaming a column in one step breaks every running copy of the old code the
moment it lands. The safe pattern has three deploys:

1. **Expand.** Add the new column. Change the code to write to both and read
   from the old one. Deploy.
2. **Backfill.** Copy old values into the new column in batches. Switch reads to
   the new column. Deploy.
3. **Contract.** Drop the old column. Deploy.

Slower, but at no point is there a version of the code that cannot run against
the version of the database in front of it. For a solo developer this matters
less than for a team, but it also makes rollbacks safe — and rollbacks are when
you least want a surprise.

### Backfilling encrypted columns

A migration cannot backfill an encrypted column, because MySQL has no keys. A
new encrypted column is added as `NULL`-able and populated by a Python script
that reads each row, decrypts, computes, re-encrypts, and writes back. Budget
for this: it is a per-row round trip to KMS unless you cache the unwrapped key
per user, which the encryption service does.

---

## Database permissions

The application connects as a role with the narrowest rights that let it work.
The template is in
[`migrations/0003_grants.sql.template`](../migrations/0003_grants.sql.template)
— it is a template rather than a migration because it contains a username you
choose and a password you generate.

The rules it encodes:

- The application may `SELECT`, `INSERT`, `UPDATE` on operational tables.
- The application may **not** `DELETE` from `support_access_grants` or
  `account_activity_log`. Audit records are append-only; code that could erase
  its own audit trail is not an audit trail.
- The application may **not** `INSERT` directly into `analytics_events`. It must
  go through `sp_analytics_record`, so the enum allowlist is unavoidable.
- The application may not `CREATE`, `ALTER` or `DROP` anything. Migrations run
  as a separate, more privileged role that is used only for that.
- No role has `SUPER` or `FILE`.

---

## Related documents

- [DATABASE.md](DATABASE.md) — the schema itself.
- [SECURITY.md](SECURITY.md) — the encryption code.
- [TESTING.md](TESTING.md) — the synthetic seed data script.
