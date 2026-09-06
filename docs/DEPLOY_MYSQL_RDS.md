# Deploying the Database to AWS RDS

**Read this when** you are creating the production database. Do this **before**
the backend, so you have a connection string for it.

Phase 1 does not use a database at all. This is the Phase 2 path.

---

## What RDS is

Amazon Relational Database Service runs MySQL for you: the machine, the
operating system, the backups, the patching. You get a hostname, a username and
a password. You do not get a server to log into, which is the point.

---

## Step 1 — Create the instance

AWS console → search **RDS** → **Create database**.

| Setting | Choose | Why |
|---|---|---|
| Creation method | **Standard create** | Easy create hides the network settings you must change |
| Engine | **MySQL** | |
| Version | Latest 8.0.x | The schema uses `utf8mb4_0900_ai_ci`, which needs 8.0 |
| Template | **Free tier**, or **Dev/Test** | |
| Instance identifier | `dungeon-master-db` | The instance's name, not the database's |
| Master username | `admin` | |
| Master password | 32+ random characters | Generate it; do not invent it |
| Instance class | `db.t4g.micro` | Two virtual processors, 1 GB. Ample for low traffic |
| Storage | 20 GB gp3 | The minimum, and far more than needed |
| Storage autoscaling | **On**, max 50 GB | Prevents a full disk; the cap prevents a runaway bill |

Generate the password properly:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Put it straight into a password manager. You will need it once, for migrations.

### Connectivity — the section that matters

| Setting | Choose |
|---|---|
| Compute resource | **Don't connect to an EC2 compute resource** |
| VPC | The default is fine |
| **Public access** | **Yes** |
| VPC security group | **Choose existing** → `dungeon-master-db` |
| Availability zone | No preference |
| Database port | 3306 |

**"Public access: Yes" looks wrong and is correct here.** It means the hostname
resolves from outside AWS. It does **not** mean anyone can connect — the
security group decides that, and it will allow exactly one address.

This is forced by the architecture: the backend is on Fly.io, outside your AWS
network. The full reasoning, the alternatives, and when to switch to a private
network are in [the cross-cloud guide](DEPLOY_CROSS_CLOUD.md). **Read that
before this step**, and create the security group described there first.

### Additional configuration

| Setting | Choose | Why |
|---|---|---|
| Initial database name | `dungeon_master` | Without this, RDS creates an instance with no database in it |
| Backup retention | **7 days** | |
| Backup window | An hour you are asleep | |
| Encryption at rest | **Enabled** | Free. Defends against physical disk theft — a different attack from the one this project's application-layer encryption addresses. Both are worth having |
| Auto minor version upgrade | **Enabled** | |
| Deletion protection | **Enabled** | Stops a mis-click destroying everything |

Then **Create database**. It takes five to ten minutes.

**Note the endpoint** when it finishes:
`dungeon-master-db.abc123.eu-west-2.rds.amazonaws.com`.

---

## Step 2 — Force TLS

By default MySQL will accept an unencrypted connection. Traffic between Fly.io
and AWS crosses the public internet, so that is not acceptable.

1. RDS → **Parameter groups** → **Create parameter group**
2. Family `mysql8.0`, name `dungeon-master-params`
3. Open it, search `require_secure_transport`, set it to **1**, save
4. RDS → **Databases** → your instance → **Modify** → set **DB parameter
   group** to the new one
5. **Apply immediately**, then reboot the instance

The database now **refuses** unencrypted connections outright, rather than
relying on every client remembering to ask.

Download Amazon's certificate bundle for the client side:

```bash
curl -o rds-ca.pem https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
```

---

## Step 3 — Run the migrations, once

A **migration** is a numbered file of instructions that builds the schema. They
run in order, once each. Skipping one leaves the application expecting a column
that does not exist; editing one that has already run makes two copies of the
database silently different, which is worse.

Run them from your laptop, using the **master** credentials — not the
application's, which deliberately cannot alter tables.

```bash
# 1. Temporarily allow your own address in the security group (see below).
# 2. Then:
cd backend
uv sync --extra db
DATABASE_URL="mysql+aiomysql://admin:PASSWORD@your-endpoint:3306/dungeon_master?ssl_ca=../rds-ca.pem" \
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

**Common failures:**

| Message | Cause | Fix |
|---|---|---|
| Hangs, then times out | Your address is not in the security group | Add it, temporarily |
| `Access denied` | Wrong password | Check the master credentials |
| `Unknown database` | No initial database name was set | Create it: `CREATE DATABASE dungeon_master;` |
| `SSL connection is required` | No `ssl_ca` in the URL | Add it |
| `has already been applied, but its contents have changed` | An applied migration was edited | Restore it and write a new numbered file instead |

**To allow your own address temporarily:** EC2 → Security Groups →
`dungeon-master-db` → Edit inbound rules → Add rule → MySQL/Aurora → Source
**My IP**.

**Remove it the same day.** Home addresses change, and the entry then belongs
to whoever receives it next. Put a reminder on your phone before you start.

---

## Step 4 — Create the application user

The application must not connect as `admin`. It needs the narrowest rights that
let it work — so that a compromise of the application cannot drop tables or
erase its own audit trail.

`migrations/0003_grants.sql.template` contains the grants. Copy it, fill in two
generated passwords, run it once as master, and **do not commit the filled-in
copy**.

What the grants encode:

- Read and write on operational tables.
- **No `DELETE` on `support_access_grants` or `account_activity_log`.** Audit
  records are append-only; code that can erase its own audit trail is not an
  audit trail.
- **No direct `INSERT` on `analytics_events`.** The only way in is
  `sp_analytics_record`, so the enum allowlist cannot be bypassed by
  application code.
- **No `CREATE`, `ALTER` or `DROP` at all.** Migrations run as master, by you,
  by hand. If the running application cannot alter tables, neither can anyone
  who compromises it.

---

## Step 5 — Verify

```sql
SHOW TABLES;                       -- 13 tables plus schema_migrations
SHOW PROCEDURE STATUS WHERE Db = 'dungeon_master';   -- 13 procedures
SELECT * FROM schema_migrations;   -- 0001 and 0002

-- The classification travels with the database itself:
SELECT COLUMN_NAME, COLUMN_COMMENT
  FROM INFORMATION_SCHEMA.COLUMNS
 WHERE TABLE_SCHEMA = 'dungeon_master' AND TABLE_NAME = 'users';
```

Every column comment should begin `PLAINTEXT:`, `ENCRYPTED:`, `HASHED:` or
`BLIND-INDEX:`. That is the privacy classification stored where it cannot drift
from the documentation.

---

## Backups, and their limits

Automated backups run daily and keep 7 days. Restoring creates a **new
instance** — you then repoint the application at it.

**What backups do not protect against, and this is the important part.** If a
user deletes their account, their key is destroyed. Restoring last week's
backup does **not** bring their data back, because the backup contains
ciphertext and the key is gone from every copy.

**That is the design working, not a fault.** It is exactly what makes deletion
honest. But it means "restore from backup" cannot undo a deletion, and nobody
should promise a user that it can.

---

## Costs

| Item | Monthly |
|---|---|
| `db.t4g.micro` | ~$12, or free for 12 months on a new account |
| 20 GB gp3 storage | ~$2 |
| Backup storage | Free up to the instance size |
| **Total** | **~$14**, or ~$2 in the free-tier year |

Free tier is 12 months from account creation, not from instance creation. See
[COSTS.md](COSTS.md).

---

## Related documents

- [The cross-cloud problem](DEPLOY_CROSS_CLOUD.md) — **read before step 1**.
- [Schema reference](../backend/docs/DATABASE.md).
- [Queries, procedures, migrations](../backend/docs/DATABASE_OPERATIONS.md).
