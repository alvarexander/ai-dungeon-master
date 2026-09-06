# Deploying the Database to Hostinger MySQL

**Read this when** you want the cheapest database that will work: the MySQL
already included with the Hostinger plan you are paying for anyway.

**Marginal cost: $0.**

**Start with Part 1.** Two things about shared hosting are unknown until you
test them, and both decide whether this option is usable at all. Ten minutes of
checking now saves you discovering it halfway through a deployment.

> This guide has not been performed. It is a careful plan written against
> Hostinger's documentation, not a transcript of a working deployment. Expect
> small differences in the hPanel wording.

---

## Why this option, and what it changes

You are already paying Hostinger to serve the Angular files. Their plans
include MySQL databases and **Remote MySQL** access, which works by
whitelisting the address your backend connects from.

That last part fits the architecture unusually well. You are already renting a
**static egress IP** from Fly.io ($3.60/month) so that AWS can allowlist your
backend. Hostinger's Remote MySQL uses the same mechanism — one address, one
allowlist entry — so you get the database for nothing and drop a whole
provider.

### What this removes

**The cross-cloud database problem disappears entirely.**
[DEPLOY_CROSS_CLOUD.md](DEPLOY_CROSS_CLOUD.md) exists because a backend on
Fly.io cannot reach a database inside an AWS private network. If the database is
on Hostinger, that problem does not exist — you whitelist an IP in hPanel and
you are done.

### What this does not remove

**You still need AWS, for KMS.** The encryption design rests on a master key
held in hardware that never releases it, and on a key policy that stops your own
administrator role decrypting user data. That is AWS Key Management Service, and
there is no Hostinger equivalent.

So the AWS bill drops from roughly $16.50 to about **$2.50**, and the
[OIDC federation setup](DEPLOY_CROSS_CUTTING.md) for reaching KMS without a
stored access key stays exactly as documented.

| | With RDS | With Hostinger |
|---|---|---|
| Database | ~$14/mo | **$0** |
| KMS + Secrets | ~$2.50/mo | ~$2.50/mo |
| Fly static egress IP | $3.60/mo | $3.60/mo |
| Cross-cloud DB problem | Real, documented | **Gone** |
| Cross-cloud KMS problem | Real | Real, unchanged |

---

## Part 1 — Verify before you commit

Two capabilities are not guaranteed on shared hosting, and this design needs
both. Test them before doing anything else.

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

### 1.3 Test A — does TLS work?

**This is the one that can rule the option out**, so do it first.

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

**If it fails** with something like `SSL connection error` or the cipher comes
back empty, **stop and read Part 4**. Do not proceed without TLS. The connection
crosses the public internet, and without it every query and every decrypted row
is readable to anything on the path. Encryption at rest does nothing about this
— it is a different attack.

**If you do not have the `mysql` client:** `brew install mysql-client`, then
follow the `PATH` instructions it prints.

### 1.4 Test B — are stored procedures allowed?

```bash
mysql -h YOUR_HOST -u YOUR_USER -p --ssl-mode=REQUIRED YOUR_DB_NAME <<'SQL'
DELIMITER $$
CREATE PROCEDURE sp_permission_test()
BEGIN
  SELECT 1 AS ok;
END$$
DELIMITER ;
CALL sp_permission_test();
DROP PROCEDURE sp_permission_test;
SQL
```

**What you want:** a row containing `1`, then silence.

**If you get** `Access denied; you need the CREATE ROUTINE privilege`, stored
procedures are blocked. That is **not fatal** — read Part 5 for what to do
instead and what it costs you.

### 1.5 Record the answer

| Check | Result | Consequence |
|---|---|---|
| TLS works | | **Blocker if no** — see Part 4 |
| MySQL 8.0+ | | Blocker if no — the schema needs it |
| `CREATE ROUTINE` | | Degraded if no — see Part 5 |

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
uv sync --extra db
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

`migrations/0003_grants.sql.template` **will not work here.** Shared hosting
does not let you `CREATE USER` or issue `GRANT` statements — Hostinger manages
users through hPanel, and the user it creates has full rights on your database.

**What you lose:** the least-privilege boundary. On RDS the application role
cannot `DROP` a table, cannot `DELETE` from the audit tables, and cannot
`INSERT` into `analytics_events` except through the stored procedure. Here it
can do all three.

**How much that matters:** less than it sounds, but it is a real reduction. It
was a defence-in-depth layer, not a primary control — the encryption is what
protects the data, and that is unchanged. But an attacker who achieves code
execution in your backend could, on this setup, erase the audit trail that
records they were there.

If that becomes unacceptable, it is one of the reasons to move to RDS.

---

## Part 3 — Backups, and one thing that will surprise you

Hostinger takes automatic backups — weekly on the cheaper plans, daily on
Business and above. Check yours under **Files → Backups**, and if it is weekly,
consider whether that is enough.

**A manual export, which is worth scripting:**

```bash
mysqldump -h YOUR_HOST -u YOUR_USER -p --ssl-mode=REQUIRED \
  --routines --single-transaction \
  u123456789_dungeon_master > backup-$(date +%F).sql
```

`--routines` is essential — without it your stored procedures are not in the
backup, and you will not notice until a restore.

### The thing that surprises people

**Restoring a backup does not undo a user's deletion.**

When someone deletes their account, their encryption key is destroyed. The
backup contains ciphertext, and the key is gone from every copy of everything.
Restoring last week's data gives you back rows nobody can read.

**That is the design working, not a fault.** It is exactly what makes deletion
honest rather than a promise. But it means "restore from backup" cannot recover
a deleted account, and nobody should ever tell a user that it can.

---

## Part 4 — If TLS does not work

Do not proceed without it. Three options, in order of preference:

**1. Ask Hostinger support.** MySQL TLS may be available and simply not
documented, or may be enabled on request. This is a two-minute question with a
good chance of a yes.

**2. Upgrade to Hostinger VPS.** On a VPS you control MySQL's configuration
directly and can set `require_secure_transport = 1`, exactly as the RDS guide
describes. Costs more than shared hosting but usually less than RDS, and you
gain stored procedures and real user grants at the same time.

**3. Go back to RDS.** [DEPLOY_MYSQL_RDS.md](DEPLOY_MYSQL_RDS.md) is written and
complete, and free for 12 months on a new AWS account. Nothing is lost by
starting there.

**What is not an acceptable option:** connecting without TLS and telling
yourself the data is encrypted anyway. The application-layer encryption protects
data *at rest*. TLS protects it *in transit*. They defend different attacks, and
neither substitutes for the other. Someone on the network path would see every
decrypted value flowing back to your backend.

---

## Part 5 — If stored procedures are blocked

Not fatal. Migration `0002` fails, `0001` still applies, and the schema is
intact. The application needs the logic moved into Python.

**What each procedure was doing, and its replacement:**

| Procedure | Replacement | Cost of moving it |
|---|---|---|
| `sp_rate_limit_hit` | An `INSERT … ON DUPLICATE KEY UPDATE` plus a `SELECT` | Two round trips instead of one. Noticeable only under load |
| `sp_user_find_by_email_bidx` | A plain `SELECT … WHERE email_bidx = ?` | None |
| `sp_user_crypto_shred` | A transaction in Python | None — same guarantees, since it is still one transaction |
| `sp_message_append` | A `SELECT … FOR UPDATE` then `INSERT` | None, provided the lock is kept |
| `sp_analytics_record` | A direct `INSERT` | **This is the real loss — see below** |
| `sp_analytics_rollup_day` | A scheduled Python job | None |
| The retention and support procedures | Python equivalents | None |

### The one that actually matters

`sp_analytics_record` was doing something the others were not: **enforcing the
analytics allowlist inside the database**, where application code cannot get
around it. Combined with denying the application direct `INSERT` on
`analytics_events`, it meant a careless future change genuinely could not write
free text into the analytics plane.

Without it, that enforcement rests entirely on `AnalyticsService.record` in
Python — which does check, thoroughly, and raises `AnalyticsRejected` on
anything undeclared. So the control still exists. It is one layer instead of
two.

**A cheap way to get most of it back:** the safety property was never really the
procedure — it was that **there is no free-text column in the analytics
schema**. That is still true, because it lives in `0001`, which applied. There
is nowhere for a stray message to land regardless of who is doing the
inserting.

**If you want the second layer back**, that is a reason to move to a VPS or
RDS. It is a reasonable thing to want and a reasonable thing to defer.

---

## When to move to RDS

Not "eventually" — these specific triggers:

- **You could not get TLS working.** Move now.
- **A second service needs the database.** Shared hosting connection limits
  become a real constraint, and one Remote MySQL allowlist is easier to reason
  about than several.
- **You need least-privilege database users.** Shared hosting cannot do it.
- **Query latency is hurting.** Shared hosting is shared; a noisy neighbour is
  someone else's problem that becomes yours.
- **You are storing anything you would be seriously distressed to lose**, and
  weekly backups are not enough.

Moving is genuinely small: export with `mysqldump --routines`, import to RDS,
change one Fly secret, redeploy. Under an hour, and the guide is already
written.

---

## Related documents

- [DEPLOY_MYSQL_RDS.md](DEPLOY_MYSQL_RDS.md) — the fallback, fully written.
- [DEPLOY_CROSS_CUTTING.md](DEPLOY_CROSS_CUTTING.md) — **still required**, for
  reaching AWS KMS without a stored access key.
- [DEPLOY_CROSS_CLOUD.md](DEPLOY_CROSS_CLOUD.md) — **not needed** if you use
  Hostinger for the database. Read it only if you move to RDS.
- [Schema reference](../backend/docs/DATABASE.md) ·
  [Queries and procedures](../backend/docs/DATABASE_OPERATIONS.md)
- [Costs](COSTS.md)
