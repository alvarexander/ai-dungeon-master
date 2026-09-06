# Running with a Local MySQL Database

**Read this when** you want your campaigns and characters to survive restarting
the server. By default the application keeps everything in memory, which is
fine for trying it out and means everything vanishes when you stop it.

This walks through installing MySQL on your own machine, creating a database,
and pointing the application at it. It assumes you have never installed a
database before.

> **Not yet verified end to end.** The code and this guide were written
> together, but no MySQL server was available on the machine where they were
> written, so the queries have not been run against a real database. Expect one
> or two small corrections. Everything else in the project is verified working.

---

## What a database actually is here

A separate program that runs in the background and stores your data on disk. It
does one thing: it keeps rows of information and finds them again quickly.

Your application talks to it over a network connection — even when both are on
the same machine, which is why it has a port number (3306) like a website has.

**Two things are running once you finish this guide:**

| | What | Where |
|---|---|---|
| The database | `mysqld`, started by your operating system | `localhost:3306` |
| Your backend | `uvicorn`, started by you | `localhost:8000` |

You start the database once and mostly forget about it. It keeps running
between reboots unless you tell it otherwise.

---

## Part 1 — Install MySQL

### macOS

```bash
brew install mysql
```

**What this does:** downloads MySQL and puts it on your machine. It does not
start it.

**What you should see:** a long stream of download progress, then a summary
mentioning `mysql` and a note about starting it with `brew services`.

**How long:** two to five minutes. It is a few hundred megabytes.

**If `brew` is not found:** install Homebrew first from <https://brew.sh>.

Then start it:

```bash
brew services start mysql
```

**What you should see:** `Successfully started mysql`.

**What this means:** MySQL is now running, and will start again automatically
whenever you restart your Mac. To stop that, `brew services stop mysql`.

### Windows

Download the MySQL Installer from
<https://dev.mysql.com/downloads/installer/>, choose **Developer Default**, and
follow the prompts. When it asks for a root password, set one and write it
down. The installer offers to run MySQL as a Windows service — say yes, so it
starts automatically.

### Linux (Debian or Ubuntu)

```bash
sudo apt update && sudo apt install mysql-server
sudo systemctl start mysql
sudo systemctl enable mysql
```

### Check it is running

```bash
mysqladmin ping
```

**What you should see:** `mysqld is alive`.

**If you see `connect to server at 'localhost' failed`:** it is installed but
not running. Go back and start it.

---

## Part 2 — Create the database and a user

A fresh MySQL install has no databases of your own, and one all-powerful
account called `root`.

**Do not let the application connect as `root`.** It would then be able to
delete every database on your machine, which is far more power than it needs.
Create a user with rights to one database and nothing else — the same
principle you would follow on a real server, practised here where mistakes are
cheap.

Open MySQL:

```bash
mysql -u root
```

On Windows, or if you set a root password: `mysql -u root -p` and enter it.

**What you should see:** a banner, then a `mysql>` prompt.

Now paste this in, **changing the password** to something of your own:

```sql
CREATE DATABASE dungeon_master
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

CREATE USER 'dm'@'localhost' IDENTIFIED BY 'change-this-password';

GRANT SELECT, INSERT, UPDATE, DELETE ON dungeon_master.* TO 'dm'@'localhost';

FLUSH PRIVILEGES;
```

Then `exit`.

**What each line does:**

| Line | Meaning |
|---|---|
| `CREATE DATABASE` | Makes an empty database. `utf8mb4` is the character set that handles every language and emoji — the older `utf8` in MySQL does not, which is a long-standing trap |
| `CREATE USER` | A login that exists only inside MySQL. `@'localhost'` means it may only connect from this machine |
| `GRANT` | Read and write rows in this one database. Note what is absent: no `CREATE`, no `DROP`, no `ALTER`. The application cannot change or destroy the schema, so a bug in it cannot either |
| `FLUSH PRIVILEGES` | Apply the changes now |

**Generate a real password** rather than inventing one:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
```

---

## Part 3 — Build the tables

The database exists but is empty. **Migrations** are numbered files of
instructions that build the structure — they live in `backend/migrations/` and
run in order, once each.

```bash
cd ~/Git/ai-dungeon-master/backend && uv sync --all-extras
```

**What this does:** installs the MySQL libraries, which are optional because
the in-memory mode does not need them.

Then, with your password in place of `change-this-password`:

```bash
cd ~/Git/ai-dungeon-master/backend && \
DATABASE_URL="mysql+aiomysql://dm:change-this-password@127.0.0.1:3306/dungeon_master" \
  uv run python scripts/migrate.py
```

**What you should see:**

```
  0001_initial_schema.sql: applying...
  0001_initial_schema.sql: done (8 statements)

All migrations applied.
```

**Common failures:**

| Message | Cause | Fix |
|---|---|---|
| `Access denied for user 'dm'` | Wrong password, or the user was not created | Redo Part 2 |
| `Unknown database 'dungeon_master'` | The `CREATE DATABASE` line did not run | Redo Part 2 |
| `Can't connect to MySQL server` | MySQL is not running | `brew services start mysql` |
| `Database libraries are not installed` | The extra was skipped | `uv sync --all-extras` |
| `has already been applied, but its contents have changed` | A migration file was edited after running | Restore it and write a new numbered file instead |

**Note `127.0.0.1` rather than `localhost`.** They usually mean the same thing,
but MySQL treats `localhost` as an instruction to connect through a local
socket file rather than the network, and the Python driver expects the network.
Using the number avoids a confusing "can't connect" that appears even though
the server is plainly running.

---

## Part 4 — Point the application at it

Open `backend/.env` and change two lines:

```
REPOSITORY_BACKEND=mysql
DATABASE_URL=mysql+aiomysql://dm:change-this-password@127.0.0.1:3306/dungeon_master
```

Then restart the backend:

```bash
cd ~/Git/ai-dungeon-master/backend && uv run uvicorn app.main:app --reload --port 8000
```

**What you should see:** the usual startup, but the warning box is now shorter —
"storage is in memory" has gone, because it is not any more.

Confirm it:

```bash
curl -s http://127.0.0.1:8000/health/ready
```

`"repository_backend": "mysql"` means it worked.

### Try it

Create a campaign in the interface. Then **stop the server and start it
again.** The campaign is still there. That is the whole point of this exercise.

---

## Part 5 — Looking at your data

This is the part worth doing, because seeing your own rows makes the rest of
the project much less abstract.

```bash
mysql -u dm -p dungeon_master
```

Then:

```sql
SHOW TABLES;

SELECT username, display_name, email, created_at FROM users;

SELECT title, tone, status, updated_at FROM campaigns;

SELECT role, LEFT(content, 60) AS beginning, created_at
  FROM messages ORDER BY seq LIMIT 10;
```

**Two things to notice, because they are the security posture made visible:**

**You can read the email addresses and the conversations.** They are stored as
ordinary text. Anyone who can connect to this database can read them, which is
why the database password matters and why a production database is put behind a
firewall.

**You cannot read anyone's password.** Try it:

```sql
SELECT username, password_hash FROM users;
```

You get something like `$argon2id$v=19$m=65536,t=3,p=2$...`. That is a one-way
fingerprint. There is no query, no tool and no amount of time that turns it back
into the password — not for an attacker, and not for you. When someone signs
in, the application fingerprints what they typed and compares. That is why
"forgot password" sends a reset link rather than telling you your old one.

---

## Everyday commands

```bash
brew services start mysql       # start it
brew services stop mysql        # stop it
brew services list              # is it running?
mysqladmin ping                 # quick health check

mysql -u dm -p dungeon_master   # connect and poke around
```

**Back to in-memory mode** at any time — set `REPOSITORY_BACKEND=memory` in
`.env` and restart. Your MySQL data stays where it is, waiting.

**Start completely over:**

```sql
DROP DATABASE dungeon_master;
```

Then redo Parts 2 and 3. Perfectly reasonable while learning; the fastest way
to get out of a confusing state.

---

## A visual tool, if you prefer

Typing SQL is not the only option. Free clients that show tables and rows in a
window:

- **TablePlus** (macOS, Windows) — the friendliest. Free tier is enough.
- **DBeaver** (all platforms) — free, more capable, denser.
- **MySQL Workbench** (all platforms) — official, thorough, dated-looking.

Connect with host `127.0.0.1`, port `3306`, user `dm`, your password, database
`dungeon_master`.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Can't connect to MySQL server on '127.0.0.1'` | Not running | `brew services start mysql` |
| `Access denied for user 'dm'@'localhost'` | Wrong password in `.env` | Check it matches what you set in Part 2 |
| `Unknown database` | Typo in the name | It is `dungeon_master`, with an underscore |
| Backend starts but every save fails | Migrations not run | Part 3 |
| `Table 'users' doesn't exist` | Same | Part 3 |
| `Incorrect string value` when saving an emoji | Database not `utf8mb4` | Recreate it with the `CHARACTER SET` line from Part 2 |
| Everything is slow to start | MySQL still booting | Wait ten seconds and retry |

**Whatever goes wrong, the backend log names it.** The application prints the
real database error rather than swallowing it, so read the terminal running
`uvicorn` before guessing.

---

## What changes when you go to production

The same schema and the same code, with four differences:

1. **The database is on another machine**, so the connection crosses a network
   and must use TLS.
2. **A firewall restricts who can connect**, rather than it being open to
   anything on your laptop.
3. **Backups run automatically.** On your machine there are none — if you
   `DROP DATABASE`, it is gone.
4. **The password is a real secret**, stored with `fly secrets set` rather than
   in a file.

See [DEPLOY_MYSQL_HOSTINGER.md](DEPLOY_MYSQL_HOSTINGER.md) for the cheapest
production option, or [DEPLOY_MYSQL_RDS.md](DEPLOY_MYSQL_RDS.md) for AWS.

---

## Related documents

- [RUNNING.md](../RUNNING.md) — starting the application.
- [backend/docs/DATABASE.md](../backend/docs/DATABASE.md) — what each table
  holds.
- [backend/docs/SECURITY.md](../backend/docs/SECURITY.md) — how data is
  protected.
