# Deploying the Backend to Fly.io

**Read this when** you are putting the Python service on the internet. Do this
**first**, before the frontend, so you have its address.

Everything here is written but **not yet performed**. In particular the
`Dockerfile` has not been built on a real machine — Docker was not installed
where this was written. Treat it as a careful plan, and expect one or two small
corrections on the first build.

---

## Why this tier needs a container and the frontend does not

The Angular app compiles to files a web server hands over unchanged — nothing
runs, so nothing needs packaging. This backend is a running Python program with
two dozen libraries, one of which needs audio tooling. Fly.io runs containers,
so it is packaged as one.

A **container** is your application bundled with everything it needs: the right
Python version, the libraries, the system tools. It behaves identically on your
laptop and on Fly.io, which removes the whole class of problem beginning "but
it works on my machine".

---

## Step 1 — Install and sign in to flyctl

`flyctl` is Fly.io's command-line tool.

```bash
brew install flyctl
```

**Expect:** installation output, then `flyctl v0.x.x` from `flyctl version`.

```bash
fly auth signup     # first time
fly auth login      # afterwards
```

**Expect:** a browser opens; after signing in the terminal says
`successfully logged in as you@example.com`.

Fly.io requires a payment card even for free usage, as anti-abuse. You will not
be charged for a small application, but set a spend limit anyway:
<https://fly.io/dashboard> → **Billing** → spending limit. Do it now, not after
a surprise.

---

## Step 2 — What `fly launch` generates, and why not to use it here

`fly launch` inspects your project and writes a `Dockerfile` and a `fly.toml`.
It is useful for a project with neither.

**This project already has both, written deliberately.** So:

```bash
cd backend
fly launch --no-deploy --copy-config --name ai-dungeon-master-api --region lhr
```

`--copy-config` uses the existing `fly.toml`. `--no-deploy` stops it deploying
before secrets are set. Answer **no** to offers of a Postgres or Redis database
— the database is on AWS.

**Change the app name.** It must be unique across all of Fly.io.

### Reading `fly.toml`

| Section | Means |
|---|---|
| `app` | Your unique name. Becomes `<name>.fly.dev` |
| `primary_region` | Where machines run. **See the warning below** |
| `[build]` | Use our `Dockerfile` |
| `[env]` | Non-secret configuration. Anything secret goes elsewhere |
| `[http_service]` | Port, HTTPS redirect, autoscaling |
| `[[http_service.checks]]` | How Fly decides the app is healthy |
| `[[vm]]` | Machine size |

> **Region choice matters more than it looks.** Pick the Fly region physically
> closest to the AWS region hosting your database, because **every database
> query pays the round trip between them**.
>
> London → AWS `eu-west-2` (London) is about 2ms. London → `us-east-1`
> (Virginia) is about 75ms. A page making ten queries is 20ms in one case and
> 750ms in the other. That is the difference between an application that feels
> instant and one that feels broken, decided by a dropdown.
>
> `lhr`→`eu-west-2`, `iad`→`us-east-1`, `ams`→`eu-west-1`.

### Memory: why 1 GB and not the default 256 MB

Two things need it:

- **The speech model holds about 1 GB** while transcribing.
- **Argon2id uses 64 MB per concurrent login.** Ten at once is 640 MB.

At 256 MB the machine is killed the moment somebody speaks, and the symptom —
`out of memory` in the logs — is not obviously connected to the microphone
button.

---

## Step 3 — Secrets

**This is the step to get right.** `fly secrets set` stores values encrypted
and injects them into the running container. They never appear in `fly.toml`,
never reach Git, and are not visible in the dashboard after being set.

```bash
fly secrets set GEMINI_API_KEY="your-real-key-here"
fly secrets set BLIND_INDEX_KEY="$(python3 -c 'import os,base64; print(base64.b64encode(os.urandom(32)).decode())')"
fly secrets set IP_HASH_SECRET="$(python3 -c 'import os,base64; print(base64.b64encode(os.urandom(32)).decode())')"
fly secrets set DATABASE_URL="mysql+aiomysql://dm_app:PASSWORD@your-db.rds.amazonaws.com:3306/dungeon_master"
fly secrets set KMS_KEY_ARN="arn:aws:kms:eu-west-2:000000000000:key/..."
fly secrets set KMS_AUDIT_KEY_ARN="arn:aws:kms:eu-west-2:000000000000:key/..."
```

**Expect:** `Secrets are staged for the first deployment` (or a restart if the
app is already running).

```bash
fly secrets list     # names and digests only, never values
```

### Why this differs from putting them in `fly.toml`

`fly.toml` is committed to version control. Git history is permanent and
frequently made public later. Rotating a key that has been committed means
rotating it everywhere *and* accepting it may already be copied.

**Guard `BLIND_INDEX_KEY` especially.** Its absence from the database is the
entire reason a stolen dump cannot be tested against a guessed email address.
Generate it once, store it in a password manager, and never log it.

---

## Step 4 — Deploy

```bash
fly deploy
```

**Expect,** over three to eight minutes:

```
==> Building image
--> Build Summary: ...
==> Pushing image to fly
==> Creating release
--> Monitoring deployment
1 desired, 1 placed, 1 healthy, 0 unhealthy
--> v1 deployed successfully
```

The first build is slow because it downloads Python, the libraries and the
speech model. Later builds reuse cached layers and take under a minute unless
dependencies changed.

**Verify:**

```bash
fly status
curl https://your-app.fly.dev/health
curl https://your-app.fly.dev/health/ready
```

`/health/ready` reports the configuration and a `warnings` list. **On a correct
production deployment that list is empty.** Anything in it names something to
fix.

---

## Step 5 — Your own domain

Needed, not optional — see the cookie-domain warning in
[the frontend guide](DEPLOY_ANGULAR_HOSTINGER.md).

```bash
fly ips allocate-v4      # about $2/month
fly ips allocate-v6      # free
fly ips list
```

At your DNS provider:

| Type | Name | Value |
|---|---|---|
| A | `api` | the IPv4 from `fly ips list` |
| AAAA | `api` | the IPv6 |

Then:

```bash
fly certs create api.yourdomain.com
fly certs show api.yourdomain.com
```

**Expect** `Certificate Authority: Let's Encrypt` and eventually
`Status: Ready`. It waits for DNS, so give it up to an hour.

Finally, update `CORS_ALLOWED_ORIGINS` and `COOKIE_DOMAIN` in `fly.toml` to
your real domains and redeploy.

---

## Step 6 — Health checks, and the mistake to avoid

Two checks, answering different questions:

| Check | Asks | On failure |
|---|---|---|
| `/health` | Is the process running? | Restart the machine |
| `/health/ready` | Can it serve requests? | Stop sending traffic; do **not** restart |

**Conflating them causes outages.** If liveness depended on the database, a
brief database blip would restart every machine — turning a two-minute
degradation into a crash loop. And restarting never fixes a missing API key.

That is why `/health` deliberately touches nothing external.

---

## Step 7 — Scaling

```bash
fly scale count 2                 # two machines
fly scale vm shared-cpu-2x        # more processor
fly scale memory 2048             # more memory
fly scale show
```

**What to change first as traffic grows:**

1. **Memory**, if transcription is used. It is the first ceiling.
2. **Machine count**, for concurrent users. But note: Phase 1's rate limiter
   counts in one process's memory, so two machines keep separate tallies and
   effectively double every limit. **Switch to the database-backed limiter
   before scaling beyond one machine.**
3. **Region count**, only once you have users far away. Each region adds
   latency to the database unless it is near AWS.

Set `min_machines_running = 1` once real people use it at unpredictable hours —
scale-to-zero saves money at the cost of a few seconds for the first visitor
after a quiet period.

---

## Reading the logs when something fails

```bash
fly logs                    # live
fly logs --no-tail          # recent
fly logs | grep correlation_id
```

Logs are JSON in production, one object per line. To find one request:

```bash
fly logs --no-tail | grep "3f1c9a7e-0b52-4d18-9a3e-77c0f1a2b8d4"
```

**This is the intended debugging workflow.** The user quotes the identifier
their error screen showed; you find every log line for that request. You do not
read their data — it is encrypted, and that is the point.

| In the logs | Means | Do |
|---|---|---|
| `Refusing to start: APP_ENV is 'production'…` | A development setting remains | Read the list; it names each one |
| `out of memory` / `OOM` | Machine too small | `fly scale memory 2048` |
| `smoke checks failed` | The app crashed at startup | `fly logs` for the real error above it |
| `gemini_quota_exhausted` | Free AI allowance spent | Expected; consider billing |
| `KeyProviderError` | KMS refused | Check the role and key policy |
| `Could not reach the AI service` | No egress, or wrong base URL | Check `GEMINI_BASE_URL` |

```bash
fly ssh console            # a shell inside the machine
fly ssh console -C "env | grep -v KEY | grep -v SECRET"
```

---

## Rollback

```bash
fly releases                       # list, newest first
fly deploy --image <previous-image-ref>
```

Or `fly releases rollback` where available.

**Practise this before you need it.** Deploy twice, roll back, confirm the
first version returns. Ten minutes now; a much better afternoon later.

**Secrets do not roll back.** They are current values, not part of a release.
If a deployment changed a secret, change it back explicitly.

---

## Related documents

- [The cross-cloud problem](DEPLOY_CROSS_CLOUD.md) — reaching the database.
- [Cross-cutting concerns](DEPLOY_CROSS_CUTTING.md) — CORS, KMS identity, order.
- [Frontend deployment](DEPLOY_ANGULAR_HOSTINGER.md) — do this second.
- [Costs](COSTS.md).
