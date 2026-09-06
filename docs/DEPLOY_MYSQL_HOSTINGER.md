# Deploying the Database to Hostinger MySQL

**Read this when** you want the cheapest database that will work: the MySQL
already included with the Hostinger plan you are paying for anyway.

**Marginal cost: $0.**

**Start with Part 1.** One thing about shared hosting is unknown until you test
it — whether the connection can use TLS — and it decides whether this option is
usable at all. Five minutes of checking now saves discovering it halfway
through a deployment.

> **Simpler than it used to be.** An earlier version of this project used
> stored procedures, which shared hosting often forbids. It no longer does —
> all the logic is in Python — so that risk is gone entirely.

> This guide has not been performed. It is a careful plan written against
> Hostinger's documentation, not a transcript of a working deployment. Expect
> small differences in the hPanel wording.

---

## Why this option, and what it changes

You are already paying Hostinger to serve the Angular files. Their plans
include MySQL databases and **Remote MySQL** access, which works by
whitelisting the address your backend connects from.

That fits this architecture well. You rent a **static egress IP** from Fly.io
($3.60/month) so the backend always connects from one known address, and
Hostinger's Remote MySQL allowlists exactly that — one address, one entry.

### What this removes

**The cross-cloud database problem disappears entirely.**
[DEPLOY_CROSS_CLOUD.md](DEPLOY_CROSS_CLOUD.md) exists because a backend on
Fly.io cannot reach a database inside an AWS private network. If the database is
on Hostinger, that problem does not exist — you whitelist an IP in hPanel and
you are done.

### What this does not need

**No AWS account at all.** The database is on Hostinger, the backend is on
Fly.io, and nothing else requires one.

| | With RDS | With Hostinger |
|---|---|---|
| Database | ~$14/mo | **$0** |
| AWS account needed | Yes | **No** |
| Fly static egress IP | $3.60/mo | $3.60/mo |
| Cross-cloud problem | Real, documented | **Gone** |

---

## Part 1 — Verify before you commit

One capability is not guaranteed on shared hosting and this design needs it:
TLS on the connection. Test it before doing anything else.

### 1.1 Get a database and a user

hPanel → **Websites → Dashboard** → **Databases → Management**.

1. **Create a new database.** Name it something like `dungeon_master`. Hostinger
   prefixes it with your account, so the real name ends up like
   `u123456789_dungeon_master` — **note the full name**, you need it in the
   connection string.
2. **Create a database user** in the same screen. Same prefixing applies.
3. **Generate a real password:**
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
   Put it straight into a password manager. Do not invent one.

### 1.2 Whitelist your own address, temporarily

hPanel → **Databases → Remote MySQL**.

Add your current home IP address. Hostinger usually offers to detect it.

**Do not tick "Any Host", and do not enter `%`.** That opens your database to
the entire internet, and MySQL ports open to the internet are found by scanners
within minutes.

### 1.3 Does TLS work?

**This is the check that can rule the option out.**

```bash
mysql -h YOUR_HOST -u YOUR_USER -p \
  --ssl-mode=REQUIRED \
  -e "SHOW STATUS LIKE 'Ssl_cipher'; SELECT VERSION();"
```

**What you want to see:**

```
+---------------+------------------------+
| Variable_name | Value                  |
+---------------+------------------------+
| Ssl_cipher    | TLS_AES_256_GCM_SHA384 |
+---------------+------------------------+
```

**A non-empty `Ssl_cipher` means TLS is working.** Also check the version is
8.0 or later — the schema uses `utf8mb4_0900_ai_ci`, which MySQL 5.7 does not
have.

**If it fails** with something like `SSL connection error`, or the cipher comes
back empty, **stop and read Part 4**. Do not proceed without TLS: the connection
crosses the public internet, and without it every query and every row that comes
back is readable to anything on the path.

**If you do not have the `mysql` client:** `brew install mysql-client`, then
follow the `PATH` instructions it prints.

### 1.4 Record the answer

| Check | Result | Consequence |
|---|---|---|
| TLS works | | **Blocker if no** — see Part 4 |
| MySQL 8.0+ | | Blocker if no — the schema needs it |

**Remove your home IP from Remote MySQL when you finish testing.** Home
addresses change, and the entry then belongs to whoever receives it next. Put a
reminder on your phone before you start.

---

## Part 2 — Connect the backend

Only once Part 1 passed.

### 2.1 Whitelist the Fly egress address

Get the address your backend actually connects *from* — which is **not** the
address people connect *to*:

```bash
fly machine list
fly machine egress-ip allocate <machine-id>     # if you have not already
fly machine egress-ip list
```

Then confirm it is genuinely what the outside world sees, rather than trusting
the dashboard:

```bash
fly ssh console -C "curl -s https://api.ipify.org"
```

**That output must match the allocated IPv4.** If it does not, stop — the
whitelist will not work, and finding out later is much worse than finding out
now.

Add that address in hPanel → **Databases → Remote MySQL**.

### 2.2 Set the connection string

```bash
fly secrets set DATABASE_URL="mysql+aiomysql://u123456789_dmapp:PASSWORD@YOUR_HOST:3306/u123456789_dungeon_master?ssl=true"
```

Note the `u123456789_` prefixes on both the user and the database name.
Forgetting them produces `Unknown database`, which is the single most common
mistake here.

Then in `backend/fly.toml`:

```toml
REPOSITORY_BACKEND = "mysql"
DATABASE_SSL_CA_PATH = "/etc/ssl/certs/ca-certificates.crt"
```

That path is the system certificate bundle, which is present in the container
because the Dockerfile is built on `python:3.12-slim`. Unlike RDS, Hostinger
uses a certificate from an ordinary public authority, so no special bundle is
needed.

**`DATABASE_SSL_CA_PATH` must not be empty.** The application refuses to start
in production when it is — a deliberate guard, because this is the setting most
easily forgotten.

### 2.3 Run the migrations

From your laptop, with your home IP temporarily whitelisted again:

```bash
cd backend
uv sync --all-extras
DATABASE_URL="mysql+aiomysql://u123456789_dmapp:PASSWORD@YOUR_HOST:3306/u123456789_dungeon_master?ssl=true" \
  uv run python scripts/migrate.py
```

**Expect:**

```
  0001_initial_schema.sql: applying...
  0001_initial_schema.sql: done (19 statements)
  0002_stored_procedures.sql: applying...
  0002_stored_procedures.sql: done (27 statements)

All migrations applied.
```

**Verify:**

```sql
SHOW TABLES;                                          -- 13 + schema_migrations
SHOW PROCEDURE STATUS WHERE Db = 'u123456789_dungeon_master';   -- 13
SELECT COLUMN_NAME, COLUMN_COMMENT
  FROM INFORMATION_SCHEMA.COLUMNS
 WHERE TABLE_NAME = 'users';
```

Every column comment should start `PLAINTEXT:`, `ENCRYPTED:`, `HASHED:` or
`BLIND-INDEX:` — the privacy classification stored where it cannot drift from
the documentation.

**Then remove your home IP from Remote MySQL again.**

### 2.4 A limitation to know about

Shared hosting does not let you run `CREATE USER` or `GRANT` — Hostinger
manages database users through hPanel, and the user it creates has full rights
on your database.

**What you lose:** on a server you control, the application connects as a user
that cannot `DROP` or `ALTER` anything, so a bug or a compromise cannot destroy
the schema. Here it can.

**How much that matters:** it is a defence-in-depth layer, not a primary
control. Worth knowing; not worth abandoning a free database over. It is one of
the reasons to move to RDS eventually.

---

## Part 3 — Backups, and one thing that will surprise you

Hostinger takes automatic backups — weekly on the cheaper plans, daily on
Business and above. Check yours under **Files → Backups**, and if it is weekly,
consider whether that is enough.

**A manual export, which is worth scripting:**

```bash
mysqldump -h YOUR_HOST -u YOUR_USER -p --ssl-mode=REQUIRED \
  --single-transaction \
  u123456789_dungeon_master > backup-$(date +%F).sql
```

`--single-transaction` takes a consistent snapshot without locking the tables,
so the application keeps working while the backup runs.

### Backups and deletion

A backup taken before somebody deleted their account still contains their data,
until that backup ages out of the retention window. That is true of essentially
every online service, and it is worth stating in any privacy policy you write
rather than glossing over.

---

## Part 4 — If TLS does not work

Do not proceed without it. Three options, in order of preference:

**1. Ask Hostinger support.** MySQL TLS may be available and simply not
documented, or may be enabled on request. This is a two-minute question with a
good chance of a yes.

**2. Upgrade to Hostinger VPS.** On a VPS you control MySQL's configuration
directly and can set `require_secure_transport = 1`, exactly as the RDS guide
describes. Costs more than shared hosting but usually less than RDS, and you
gain a least-privilege database user at the same time.

**3. Go back to RDS.** [DEPLOY_MYSQL_RDS.md](DEPLOY_MYSQL_RDS.md) is written and
complete, and free for 12 months on a new AWS account. Nothing is lost by
starting there.

**What is not an acceptable option:** connecting without TLS and telling
yourself the data is encrypted anyway. The application-layer encryption protects
data *at rest*. TLS protects it *in transit*. They defend different attacks, and
neither substitutes for the other. Someone on the network path would see every
decrypted value flowing back to your backend.

---

## Part 5 — What is no longer a problem

An earlier version of this project used thirteen stored procedures, and shared
hosting frequently forbids creating them. That risk is gone: all the logic now
lives in Python, and the schema is seven plain tables with no procedures,
triggers or functions.

If you read an older version of this guide that told you to test for
`CREATE ROUTINE` permission, you can ignore it.

---

## When to move to RDS

Not "eventually" — these specific triggers:

- **You could not get TLS working.** Move now.
- **A second service needs the database.** Shared hosting connection limits
  become a real constraint, and one Remote MySQL allowlist is easier to reason
  about than several.
- **You need a least-privilege database user.** Shared hosting cannot do it.
- **Query latency is hurting.** Shared hosting is shared; a noisy neighbour is
  someone else's problem that becomes yours.
- **You are storing anything you would be seriously distressed to lose**, and
  weekly backups are not enough.

Moving is genuinely small: `mysqldump` the database, import it into RDS, change
one Fly secret, redeploy. Under an hour, and the guide is already written.

---

## Related documents

- [DEPLOY_MYSQL_RDS.md](DEPLOY_MYSQL_RDS.md) — the fallback, fully written.
- [DEPLOY_CROSS_CUTTING.md](DEPLOY_CROSS_CUTTING.md) — CORS, secrets, TLS and
  rollback.
- [DEPLOY_CROSS_CLOUD.md](DEPLOY_CROSS_CLOUD.md) — **not needed** if you use
  Hostinger for the database. Read it only if you move to RDS.
- [Schema reference](../backend/docs/DATABASE.md) ·
  [Queries and migrations](../backend/docs/DATABASE.md)
- [Costs](COSTS.md)
