# Costs

**Read this when** you want to know what running this costs, what the free
tiers actually cover, and — more usefully — **what breaks first as traffic
grows**.

All figures are approximate and in US dollars per month, at list prices as
understood when this was written. Check current pricing before relying on any
of them.

---

## The short answer

| Stage | Monthly |
|---|---|
| Running locally | **$0** |
| Deployed, database on Hostinger | **~$7** |
| Deployed, database on AWS RDS, first 12 months | **~$11** |
| Deployed, database on AWS RDS, after the free tier | **~$25** |
| A few hundred active users | **~$40** |

The cheapest working deployment is roughly **$7/month**: the Hostinger plan you
already pay for, a small Fly.io machine, and a static egress IP. **No AWS
account is needed at all** on that path.

---

## Line by line

### Frontend — Hostinger

| Item | Monthly | Notes |
|---|---|---|
| Shared hosting | $3–$10 | Whatever plan you already have |
| TLS certificate | $0 | Free Let's Encrypt |
| Bandwidth | $0 | The whole app is under 300 kB compressed |

If you already pay for Hostinger for something else, the marginal cost is
effectively zero. A static site is very cheap to serve.

### Backend — Fly.io

| Item | Monthly | Notes |
|---|---|---|
| `shared-cpu-1x`, 1 GB | ~$5.70 | Awake continuously |
| — with scale-to-zero | ~$2–3 | Billed only while running |
| Dedicated IPv4 (ingress) | $2 | Needed for your own domain |
| **Static egress IPv4** | **$3.60** | **Needed so AWS can allowlist you** |
| IPv6 | $0 | |
| Bandwidth | $0 | Generous free allowance; this app sends little |

**Subtotal: roughly $11, or $8 with scale-to-zero.**

**Why 1 GB rather than the 256 MB default.** Two things need it: the speech
model holds about 1 GB while transcribing, and Argon2id uses 64 MB per
concurrent login. At 256 MB the machine is killed the first time somebody uses
the microphone — and the symptom, `out of memory` in the logs, is not obviously
connected to a microphone button.

**Why the egress IP is not optional.** Fly's *inbound* address is not the
address your outbound traffic comes from, and the default outbound addresses
change. Without a static one, your AWS security group silently stops matching
at some point, with no deployment to blame. See
[the cross-cloud guide](DEPLOY_CROSS_CLOUD.md).

### Database — two options

**Cheapest: the MySQL already included with Hostinger — $0.**

You are already paying Hostinger for the frontend, and their plans include
MySQL with Remote MySQL access by IP allowlist — the same mechanism the Fly
static egress IP already exists for. It also removes the cross-cloud database
problem completely.

Two things must be verified first, because shared hosting does not guarantee
it: whether the connection can use TLS. That check takes five minutes and is
Part 1 of
[DEPLOY_MYSQL_HOSTINGER.md](DEPLOY_MYSQL_HOSTINGER.md).

**Fallback: AWS RDS**

| Item | Monthly | Free tier |
|---|---|---|
| `db.t4g.micro` | ~$12 | Free for 12 months on a new account |
| 20 GB gp3 storage | ~$2 | 20 GB free for 12 months |
| Backups (7 days) | $0 | Free up to the instance size |
| Data transfer out | ~$0.50 | Small; queries return little |

**Subtotal: ~$14.50, or ~$0.50 during the free-tier year — or $0 on
Hostinger.**

The AWS free tier runs 12 months **from account creation**, not from creating
the instance. If your account is already older than that, you pay from day one.

### Google Gemini

**$0 on the free tier**, which is what makes this project viable to run for
yourself.

**But read [GEMINI.md](../backend/docs/GEMINI.md) before letting anyone else
use it.** Google's free-tier terms permit them to use submitted prompts to
improve their products, and state that human reviewers may read them.

**If real people other than you will use this, enable billing.** The paid tier
forbids training on your prompts, and at this application's traffic costs
pennies:

| Users | Turns/month | Approximate cost |
|---|---|---|
| Just you | ~500 | under $0.50 |
| 10 friends | ~5,000 | ~$3 |
| 100 users | ~50,000 | ~$30 |

Based on roughly 800 tokens in and 250 out per turn on a Flash model. Enabling
billing is the single best value purchase in this entire list — it is the only
complete fix for the one place personal data genuinely leaves your control.

### Cloudflare

**$0.** The free plan covers DDoS protection, TLS, five firewall rules, and the
`CF-IPCountry` header the analytics plane relies on for country-only geography.
More than enough.

---

## Totals

### First 12 months, new AWS account

| | |
|---|---|
| Hostinger | $3 |
| Fly.io | $8 (scale-to-zero) |
| RDS | $0.50 |
| Gemini | $0 |
| **Total** | **~$14** |

### After the free tier, on RDS

| | |
|---|---|
| Hostinger | $3 |
| Fly.io | $11 |
| RDS | $14.50 |
| Gemini (paid, small) | $3 |
| **Total** | **~$31.50** |

### With the database on Hostinger

| | |
|---|---|
| Hostinger (hosting + MySQL) | $3 |
| Fly.io | $11 |
| Database | **$0** |
| Gemini (paid, small) | $3 |
| **Total** | **~$17** |

**No AWS account at all** on this path — which is one fewer provider, one fewer
bill, and one fewer console to learn.

---

## What the privacy design costs

Worth separating out, because it is a real number and it should be a conscious
choice rather than a surprise.

| Control | Extra cost | What it buys |
|---|---|---|
| **Local speech-to-text** | **~$4/month** — 1 GB instead of 256 MB | Voice recordings never reach Google |
| Argon2id password hashing | $0, but 64 MB per concurrent login | A stolen database does not hand over passwords |
| TLS, firewall, limited database user | $0 | Access control on the data |
| Log redaction, analytics with no free-text column | $0 | Credentials stay out of logs; nothing typed reaches analytics |

**About $4 a month.** Almost every protection here costs nothing but the
decision to do it that way. The single exception is transcribing audio on your
own server rather than sending it to Google, which needs a bigger machine.

---

## What breaks first as you grow

More useful than the totals. In order.

### 1. The Gemini free tier — at about 10 daily users

**The first thing you will hit, by a wide margin.** Free-tier limits for a Flash
model have commonly sat around 250 requests per day. One turn is one request,
so that is a few hours of solo play — or roughly ten people having a short
session each.

**Symptom:** players see "the free AI allowance has been used up".
**Fix:** enable billing. About $3/month at that scale.

### 2. Rate limiting, the moment you run two machines — at about 50 concurrent users

Rate limits are counted in one process's memory. Two machines keep separate
tallies, so every limit silently doubles.

**Symptom:** none. It quietly stops working, which is the worst kind.
**Fix:** move the counters into the database **before** scaling past one
machine.

### 3. Memory during transcription — at about 5 simultaneous speakers

Each transcription holds roughly 1 GB. Several at once exhausts a 1 GB machine.

**Symptom:** `out of memory` in `fly logs`; the machine restarts.
**Fix:** `fly scale memory 2048` (+$3), or a queue so transcriptions run one at
a time.

### 4. Argon2id memory during login spikes — at about 15 simultaneous logins

64 MB each. Fifteen at once is nearly a gigabyte, on top of everything else.

**Symptom:** out-of-memory errors clustered at busy times.
**Fix:** more memory, or more machines.

### 5. The database — a long way off

`db.t4g.micro` handles thousands of users for this workload. Queries are
simple, and the encryption means there are no expensive text searches to run.

**Symptom:** slow queries; processor credits exhausted.
**Fix:** `db.t4g.small` (+$12).

### 6. Bandwidth — effectively never

The whole application is under 300 kB compressed and API responses are small.

---

## Keeping the bill from surprising you

1. **Set a Fly.io spend limit** — <https://fly.io/dashboard> → Billing. Do it
   before deploying, not after a surprise.
2. **Set an AWS budget alert** at $20/month. Billing → Budgets. The most useful
   ten minutes you will spend in the AWS console.
3. **Cap Gemini** in Google Cloud Console once billing is enabled.
4. **Turn on `deletion_protection`** for RDS — a mis-click that destroys the
   database has a cost measured in more than dollars.
5. **Watch `quota_exhaustions`** in the aggregate counters. It tells you the AI
   free tier is biting before your players tell you.

The realistic runaway risk here is not the infrastructure — it is Gemini usage
if the application is left open to the public without a cap. Everything else is
a fixed monthly amount that cannot spike.
