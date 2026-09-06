# Database

**Read this when** you need to know what tables exist, how to query them, or
how to change the schema.

To run MySQL on your own machine and look at your own data, follow
[docs/LOCAL_MYSQL.md](../../docs/LOCAL_MYSQL.md). The authoritative schema is
[`migrations/0001_initial_schema.sql`](../migrations/0001_initial_schema.sql).

---

## Two storage backends

| `REPOSITORY_BACKEND` | What it is | Data survives restart? |
|---|---|---|
| `memory` (default) | Python dictionaries | **No** |
| `mysql` | A real database | Yes |

Both satisfy the same interfaces in `app/repositories/base.py`, so nothing
above that layer knows which one it got. Switching is one line in `.env`.

The in-memory store is the default so that a newcomer can get the application
running without installing a database first — that is the point at which people
give up.

---

## The tables

Seven, plus bookkeeping.

```
users
  └── campaigns            (ON DELETE CASCADE)
        └── characters     (ON DELETE CASCADE)
        └── game_sessions  (ON DELETE CASCADE)
              └── messages (ON DELETE CASCADE)

analytics_events           (ON DELETE SET NULL — see below)
schema_migrations
```

### What each holds

| Table | Holds | Notes |
|---|---|---|
| `users` | Accounts | `password_hash` is Argon2id and is never recoverable |
| `campaigns` | One ongoing story | Title, premise, tone, ruleset |
| `characters` | Player characters | The sheet is a JSON column |
| `game_sessions` | One sitting at the table | Turn count |
| `messages` | The transcript | `seq` numbers them within a session |
| `analytics_events` | Usage counts | **No free-text column exists** |
| `schema_migrations` | Which migrations have run | With a checksum |

### Three schema choices worth understanding

**`BINARY(16)` for identifiers.** A UUID stored as sixteen raw bytes rather
than a thirty-six character string. Less than half the size, and size matters
because every index holds a copy. `_to_db` and `_from_db` in `sql.py` convert at
the boundary, so nothing else has to think about it.

**Identifiers are random, not sequential.** A counting identifier leaks how many
accounts exist and in what order they were created — and, more importantly,
lets somebody read other people's records by guessing the next number.

**The character sheet is a JSON column.** Sheets gain fields constantly, and a
JSON column absorbs that without a migration every time. The two fields actually
queried — class and level — are real columns.

### Cascades, and the one exception

`ON DELETE CASCADE` means that when a row goes, everything belonging to it goes
too. Deleting an account removes its campaigns, characters, sessions and
messages in one statement, and **cannot leave orphans behind** — which a
hand-written cleanup routine can, the first time somebody adds a table and
forgets to update it.

`analytics_events` is deliberately different: `ON DELETE SET NULL`. The event
survives with no owner, so the totals stay correct while the person disappears
from them. Business metrics should not drop retroactively every time somebody
closes their account.

### Analytics has no free-text column

Every field is an enumerated value, a number, a boolean or a timestamp. That is
a mechanism rather than a promise: a careless change later cannot start
recording what players typed, because there is physically nowhere for it to go.

---

## Querying

Every query lives in `app/repositories/sql.py`, written out in full. You can
copy one into a database client and run it.

### The rule that is not negotiable

**Named parameters, never string joining:**

```python
# Right — the driver sends the query and the value separately.
text("SELECT ... FROM users WHERE email = :email"), {"email": email}

# Wrong. This is SQL injection, and it is the most common serious web
# vulnerability. Never do this, however certain you are about the input.
text(f"SELECT ... FROM users WHERE email = '{email}'")
```

### The main access patterns

**Find an account for sign-in:**

```sql
SELECT user_id, username, display_name, email, email_verified,
       password_hash, status, created_at
  FROM users WHERE email = :email LIMIT 1;
```

**List someone's campaigns:**

```sql
SELECT campaign_id, user_id, title, premise, ruleset, tone, status,
       created_at, updated_at
  FROM campaigns
 WHERE user_id = :user_id AND status <> 'archived'
 ORDER BY updated_at DESC LIMIT :limit OFFSET :offset;
```

Note `user_id` is **in the query**, not checked afterwards. A campaign
belonging to somebody else simply does not come back. Every read in this
codebase works that way.

**Read a page of a conversation:**

```sql
SELECT message_id, seq, role, content, input_mode, token_count, created_at
  FROM messages
 WHERE game_session_id = :sid AND user_id = :user_id AND seq > :after
 ORDER BY seq ASC LIMIT :limit;
```

**Append a message, safely:**

```sql
SELECT COALESCE(MAX(seq), 0) + 1 FROM messages
 WHERE game_session_id = :sid FOR UPDATE;
```

`FOR UPDATE` locks those rows until the transaction commits. Without it, two
requests arriving together could both read "the last one was 6" and both try to
write 7 — and the unique key on `(game_session_id, seq)` would reject one of
them, losing a message.

**Delete an account** — one statement, cascades do the rest:

```sql
DELETE FROM users WHERE user_id = :user_id;
```

**See how the product is doing:**

```sql
SELECT DATE(occurred_at) AS day, event_name, COUNT(*) AS n
  FROM analytics_events
 WHERE occurred_at >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL 30 DAY)
 GROUP BY day, event_name ORDER BY day DESC;
```

---

## Migrations

### What a migration is, and why you cannot skip one

The database starts empty. A migration is a numbered file of instructions that
changes its structure. They run in order, once each, and are **never edited
after they have run anywhere real.**

Skip one and the application expects a column that does not exist, failing on
the first request that touches it. Edit one that has already run and your
laptop and the server end up with silently different schemas — considerably
worse than an error, because nothing tells you.

`scripts/migrate.py` records each file with a checksum and **refuses to
continue** if an applied file has changed.

### Running them

```bash
cd backend && uv sync --all-extras
DATABASE_URL="mysql+aiomysql://dm:PASSWORD@127.0.0.1:3306/dungeon_master" \
  uv run python scripts/migrate.py
```

### Changing the schema

1. Write a new numbered file, e.g. `0002_add_campaign_notes.sql`. **Never edit
   an existing one.**
2. Update this document in the same commit.
3. Run it locally and confirm the application still starts.
4. Run it against production.

### Expand and contract, for changes that cannot break

Renaming a column in one step breaks every running copy of the old code the
moment it lands. The safe pattern has three deploys:

1. **Expand.** Add the new column. Write to both, read the old one.
2. **Backfill.** Copy the values across. Switch reads to the new column.
3. **Contract.** Drop the old column.

Slower, but at no point is there a version of the code that cannot run against
the version of the database in front of it — which is also what makes a
rollback safe.

**Migrations do not roll back.** To undo one, write a new migration that
reverses it. This is why you should never drop a column the current code still
reads: the rollback then becomes impossible rather than merely awkward.

---

## Database permissions

The application connects as a user that can read and write rows and nothing
else:

```sql
GRANT SELECT, INSERT, UPDATE, DELETE ON dungeon_master.* TO 'dm'@'localhost';
```

No `CREATE`, no `DROP`, no `ALTER`. Migrations run separately with different
credentials. If the running application cannot drop a table, neither can
anyone who compromises it.

---

## Related documents

- [docs/LOCAL_MYSQL.md](../../docs/LOCAL_MYSQL.md) — install MySQL and look at
  your data.
- [SECURITY.md](SECURITY.md) — how data is protected.
- [ARCHITECTURE.md](ARCHITECTURE.md) — where the repository layer sits.
