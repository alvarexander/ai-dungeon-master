# The Cross-Cloud Problem

**Read this when** you are connecting the Fly.io backend to a database in
**AWS RDS**.

> **You may not need this document at all.** It exists because a backend on
> Fly.io cannot reach a database inside an AWS private network. If you put the
> database on [Hostinger](DEPLOY_MYSQL_HOSTINGER.md) instead, that problem does
> not arise — you whitelist one IP in hPanel and you are finished. You will
> still need [the KMS half](DEPLOY_CROSS_CUTTING.md) of the cross-cloud story,
> because the encryption keys stay in AWS regardless.
**This is the hardest part of the whole deployment**, and the part where a
wrong choice is most expensive to undo, so it gets its own document.

---

## The problem, plainly

Your backend runs on Fly.io. Your database runs on AWS. These are two different
companies with two entirely separate networks.

Inside AWS this would be easy: put both in the same private network, mark the
database "not publicly accessible", and they talk over wiring nobody else can
reach. That is the normal advice, and it is the first thing every guide tells
you to do.

**You cannot do it.** Fly.io machines are not inside your AWS network. A
database marked private is private *from them too*, and your application simply
cannot connect.

So the question is: **how does a machine outside AWS reach a database inside
it, without leaving that database open to the world?**

---

## First, the thing that makes this less frightening

Your security does not rest on the answer.

The threat model already assumes **an attacker has the entire database** — a
leaked snapshot, a stolen backup, a dishonest administrator. That is precisely
why every personal column is ciphertext and the keys live somewhere else.

Network isolation here is a useful extra wall. It is not *the* wall.

That matters because it changes the decision. You are not choosing between
"secure" and "insecure". You are choosing how much operational complexity to
take on for an additional layer, on top of a design that already assumes this
layer fails.

---

## The four options

### Option 1 — Public endpoint, locked to one address

Mark RDS publicly accessible, then use an AWS security group to allow exactly
one source address: a **static egress IP** rented from Fly.io.

**"Publicly accessible" oversells the risk.** A security group is a firewall.
Set to one address and one port, the database does not answer anyone else — it
does not respond to a scan, it does not offer a login prompt. It is a locked
door in an alley whose address one person knows.

**The catch, and it is the thing people get wrong.** Fly.io's *inbound* address
(what `fly ips allocate-v4` gives you) is **not** the address your outbound
traffic comes from. By default outbound traffic uses shared addresses that can
change when a machine is recreated — and then your allowlist silently stops
matching, at 3am, with no deployment to blame.

Fly.io sells **static egress IPs** for this, at **$3.60/month** for an
app-scoped IPv4. That is the piece that makes this option viable rather than
fragile.

| | |
|---|---|
| **Cost** | $3.60/month |
| **Setup** | ~30 minutes |
| **Moving parts** | None beyond what you already run |
| **Fails when** | You forget the egress IP is separate from the ingress one |

### Option 2 — Tailscale

Tailscale builds a private network across machines anywhere, managing keys and
connections for you. Install it in the Fly container and run a **subnet router**
inside your AWS network that advertises the database's address.

RDS then stays fully private — not publicly resolvable at all.

**What it actually costs you:** a second always-on machine in AWS (a `t4g.nano`
at roughly $3/month), Tailscale in the container (which complicates the
Dockerfile and needs an auth key as a secret), and a subnet route to approve.
That EC2 instance is now something that can break at three in the morning, and
when it does, your application cannot reach its database.

| | |
|---|---|
| **Cost** | ~$3/month EC2, Tailscale free tier |
| **Setup** | 2–3 hours |
| **Moving parts** | A router machine, an agent in the container, an auth key |
| **Fails when** | The router instance dies, or the auth key expires |

### Option 3 — Raw WireGuard

The same shape as Tailscale, except you manage the keys, the routing and the
recovery yourself.

Tailscale *is* WireGuard with the tedious parts handled. Doing it by hand buys
independence from Tailscale and costs you every piece of operational work they
were doing. **For a solo developer this is the wrong trade** — the failure mode
is a key exchange you set up months ago and no longer remember.

### Option 4 — Bastion or SSH tunnel

A small EC2 instance you connect through.

**Not suitable for production.** An SSH tunnel is a single long-lived process
that dies quietly — when it does, every database query fails until somebody
notices and restarts it by hand. Fine for a one-off migration from your laptop;
not a foundation.

---

## The recommendation

**Option 1: public endpoint, locked to a Fly.io static egress IP, TLS
required.**

For one backend, one developer and low traffic, it is right for four reasons:

1. **Fewest moving parts.** No second machine to keep alive. The things that
   break are the things you are already running.
2. **The extra layer is not carrying your security.** Everything sensitive is
   already ciphertext, and the keys are not in the database.
3. **It is cheaper**, both in money and in the attention an extra always-on
   machine demands.
4. **It is easy to leave.** Moving to Tailscale later changes a connection
   string and a firewall rule. This is a cheap decision to reverse, which is
   exactly the kind you should not agonise over.

### When to move to Option 2

Upgrade when any of these becomes true:

- **A second service needs the database.** Two allowlist entries to keep in step
  is where this starts to creak.
- **Somebody else joins**, and needs their own access.
- **A compliance requirement** says the database must not be publicly routable.
- **You are managing more than about three AWS resources** that Fly needs to
  reach. At that point a private network is genuinely simpler.

---

## Step by step: the recommended path

### 1. Allocate a static egress IP on Fly.io

```bash
fly machine list
fly machine egress-ip allocate <machine-id>
fly machine egress-ip list
```

**Expect** an IPv4 and an IPv6. Note the **IPv4** — that is what goes in the
security group.

**Two limits worth knowing.** Egress IPs are **per region**: a machine can only
use one allocated in its own region, so adding a region means adding an IP. And
each supports up to 64 machines, which you will not reach.

**Verify it is really what AWS will see**, rather than trusting the dashboard:

```bash
fly ssh console -C "curl -s https://api.ipify.org"
```

**That output must match the allocated IPv4.** If it does not, stop — the
allowlist will not work, and finding out later is much worse.

### 2. Create the security group

In the AWS console, **VPC → Security Groups → Create security group**.

- **Name:** `dungeon-master-db`
- **VPC:** the one your RDS instance is in
- **Inbound rules:** one rule only:

| Type | Protocol | Port | Source |
|---|---|---|---|
| MySQL/Aurora | TCP | 3306 | `<your Fly egress IPv4>/32` |

**The `/32` matters.** It means exactly that one address. `/24` would be 256
addresses, most of them belonging to strangers.

**Outbound:** leave the default.

**Do not add `0.0.0.0/0`, ever**, not even briefly while debugging. That is
"the entire internet", and a MySQL port open to the internet is found by
scanners within minutes.

Add your own address temporarily if you need to run migrations from your
laptop, and **remove it the same day**. Home addresses change, and the entry
then belongs to whoever gets it next.

### 3. Configure RDS

When creating the instance (see [the RDS guide](DEPLOY_MYSQL_RDS.md)):

- **Public access: Yes.** Counter-intuitive, and correct — it means "resolvable
  from outside", not "open". The security group decides who may connect.
- **Security group:** the one you just made. Remove the default.
- **Subnet group:** public subnets, or it will not be reachable regardless.

### 4. Require TLS — not optional

TLS encrypts the connection so nobody between Fly.io and AWS can read or alter
it. Traffic is crossing the public internet; without TLS, every query and every
row is readable to anything on the path.

**Enforce it on both sides**, so neither can silently fall back.

On the database, create a parameter group with `require_secure_transport = 1`.
MySQL then **refuses** an unencrypted connection outright.

Download Amazon's certificate bundle:

```bash
curl -o rds-ca.pem https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
```

And reference it in the connection:

```
DATABASE_URL=mysql+aiomysql://dm_app:PASSWORD@host:3306/dungeon_master?ssl_ca=/app/certs/rds-ca.pem
```

The application also refuses to start in production if `DATABASE_SSL_CA_PATH`
is empty — a third guard, because this is the setting most easily forgotten.

### 5. Verify

```bash
fly ssh console
python -c "
import socket
s = socket.create_connection(('your-db.rds.amazonaws.com', 3306), timeout=5)
print('connected:', s.getpeername())
s.close()"
```

**Expect** `connected: ('x.x.x.x', 3306)`.

**A hang means the security group is wrong** — most often the egress IP does not
match what AWS sees. Go back to the `ipify` check in step 1.

Then confirm it is refused from anywhere else:

```bash
nc -zv -w 5 your-db.rds.amazonaws.com 3306     # from your laptop
```

**Expect this to time out.** If it connects, your security group is too open —
fix it before going further.

---

## Keeping it working

| Risk | Warning sign | Response |
|---|---|---|
| Egress IP changes | Sudden connection timeouts, no deploy to blame | Re-run the `ipify` check; update the security group |
| Adding a Fly region | New region cannot connect | Allocate an egress IP there too and add it |
| Certificate expiry | TLS handshake failures | Amazon rotates the bundle; refresh it yearly |
| Someone "temporarily" widens the group | Nothing — it silently works | Review inbound rules monthly; there should be exactly one |

That last row is the realistic failure. Nobody opens a database to the internet
deliberately; they open it for ten minutes to debug something and then get
distracted. Put a monthly reminder in your calendar to look at that rule.

---

## Related documents

- [RDS setup](DEPLOY_MYSQL_RDS.md) — creating the database.
- [Fly.io deployment](DEPLOY_PYTHON_FLYIO.md) — the backend.
- [Cross-cutting concerns](DEPLOY_CROSS_CUTTING.md) — the *other* cross-cloud
  problem: how the application authenticates to AWS KMS without a stored key.
