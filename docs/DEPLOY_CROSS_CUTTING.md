# Cross-Cutting Deployment Concerns

**Read this when** you are dealing with something that spans all three tiers:
CORS, how the backend authenticates to AWS, TLS and security headers, the order
to deploy in, and how to roll each tier back.

---

## CORS across three origins

### What CORS is, and why the browser insists

A web page loaded from one address is not allowed to read responses from a
different address, unless that other address explicitly permits it. The rule is
enforced by the browser, not by either server.

**Why it exists.** Without it, any page you visited could quietly make requests
to your bank, your webmail or your employer's intranet — with your cookies
attached — and read the replies. The browser refuses by default, and a server
must opt in for a specific origin.

**Why it is unavoidable here.** Three separate hosts:

```
https://app.yourdomain.com     Angular       (Hostinger)
https://api.yourdomain.com     Python        (Fly.io)
        the database                          (AWS, never touched by a browser)
```

The page is on one, the API on another. Every single request is cross-origin.
A single-server application never meets CORS at all; this architecture meets it
on request one.

### Configuration

On the backend, in `fly.toml`:

```
CORS_ALLOWED_ORIGINS = "https://app.yourdomain.com"
```

Rules that will save you an afternoon:

- **Exact match, including scheme and port.** `https://app.yourdomain.com` does
  not permit `http://app.yourdomain.com` or `https://www.app.yourdomain.com`.
- **No trailing slash.** The application strips one defensively, but do not
  rely on it.
- **Never `*`.** The settings validator refuses it, and browsers refuse a
  wildcard combined with credentials anyway — producing a confusing runtime
  failure rather than a clear startup one.
- **Both `www` and bare?** List both, comma-separated. Better: redirect one to
  the other at the DNS or hosting layer and have one canonical address.

`allow_credentials=True` is set, which is what lets the browser send the XSRF
cookie. It is also why a wildcard is forbidden.

### Reading a CORS failure

The browser console says something like:

> Access to fetch at 'https://api.yourdomain.com/api/v1/campaigns' from origin
> 'https://app.yourdomain.com' has been blocked by CORS policy: No
> 'Access-Control-Allow-Origin' header is present.

**Read it carefully — it names both origins.** Compare the "from origin" value
character by character against `CORS_ALLOWED_ORIGINS`. Nine times in ten the
difference is `http` versus `https`, a `www`, or a trailing slash.

A useful diagnostic:

```bash
curl -sI -X OPTIONS https://api.yourdomain.com/api/v1/campaigns \
  -H "Origin: https://app.yourdomain.com" \
  -H "Access-Control-Request-Method: POST" | grep -i access-control
```

You want `access-control-allow-origin` echoing your origin back, and
`access-control-allow-credentials: true`.

### The cookie-domain trap, again

CORS is not the only cross-origin rule. Even with CORS correct, **the browser
will not let the frontend read a cookie set by an unrelated domain.**

```
app.yourdomain.com  +  api.yourdomain.com  +  COOKIE_DOMAIN=.yourdomain.com   ✓
app.yourdomain.com  +  my-api.fly.dev      +  anything                        ✗
```

The second arrangement passes every CORS check and then fails every
state-changing request with a 403. It is the single most likely thing to break
your first deployment.

---

## The second cross-cloud problem: authenticating to AWS

The first cross-cloud problem is reaching the database
([its own document](DEPLOY_CROSS_CLOUD.md)). This is the other one, and it is
less obvious.

**The problem.** Code running inside AWS gets credentials automatically. Our
code runs on Fly.io, so it does not. But it must call KMS to unwrap user keys —
without which it cannot read any user data at all.

### The easy answer, and why not to use it

Create a permanent IAM access key and store it with `fly secrets set`.

It works. But that key is a password that never expires. If it leaks — into a
log, a screenshot, a backup, a support ticket — it grants access until somebody
notices and revokes it. And it sits in one place, so every machine shares one
credential.

### The right answer: OIDC federation

Fly.io runs an identity service that hands each running machine a short-lived,
signed document proving "I am machine X of app Y in organisation Z". AWS can be
configured to trust that service.

The backend presents the document to AWS Security Token Service and receives
temporary credentials, **valid for fifteen minutes**, issued per machine.

**There is no long-lived secret to leak.** That is the whole point.

### Setting it up

**1. Add Fly.io as an identity provider in AWS.**

IAM → **Identity providers** → **Add provider** → **OpenID Connect**.

| Field | Value |
|---|---|
| Provider URL | `https://oidc.fly.io/<your-org-slug>` |
| Audience | `sts.amazonaws.com` |

Your organisation slug comes from `fly orgs list`.

**2. Create the role the application will assume.**

IAM → **Roles** → **Create role** → **Web identity**, choosing the provider you
just added. Then edit its trust policy so that only *your* app can assume it:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/oidc.fly.io/YOUR_ORG" },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "oidc.fly.io/YOUR_ORG:aud": "sts.amazonaws.com",
        "oidc.fly.io/YOUR_ORG:sub": "YOUR_ORG:ai-dungeon-master-api"
      }
    }
  }]
}
```

**The `sub` condition is essential.** Without it, *any* application in your Fly
organisation could assume this role.

**3. Give the role only what it needs.**

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["kms:GenerateDataKey", "kms:Decrypt"],
    "Resource": "arn:aws:kms:REGION:ACCOUNT:key/YOUR_KEY_ID"
  }]
}
```

Two actions, one key. Not `kms:*`, not `Resource: "*"`.

**4. Tell the application.** Already in `fly.toml`:

```
AWS_ROLE_ARN = "arn:aws:iam::000000000000:role/dungeon-master-app"
AWS_WEB_IDENTITY_TOKEN_FILE = "/.fly/oidc_token"
```

The AWS SDK sees these and does the rest. No code change.

### Key custody: denying yourself access

The project requires that your everyday administrator role **cannot** decrypt
user data. On the KMS key policy:

```json
{
  "Sid": "DenyDecryptToHumans",
  "Effect": "Deny",
  "Principal": "*",
  "Action": ["kms:Decrypt", "kms:GenerateDataKey"],
  "Resource": "*",
  "Condition": {
    "ArnNotEquals": {
      "aws:PrincipalArn": [
        "arn:aws:iam::ACCOUNT:role/dungeon-master-app",
        "arn:aws:iam::ACCOUNT:role/dungeon-master-breakglass"
      ]
    }
  }
}
```

**This is deliberately inconvenient.** It means that if your own AWS
credentials are phished, the attacker gets your infrastructure but not your
users' data.

**Set up the break-glass role before you need it**, requiring multi-factor
authentication, with a CloudTrail alarm on every `Decrypt` it performs. And
practise using it once, so that the first time is not during an incident.

---

## TLS and security headers

| Tier | TLS from | Headers set by |
|---|---|---|
| Hostinger | Free Let's Encrypt in hPanel; enable **Force HTTPS** | `.htaccess` |
| Fly.io | Automatic; `force_https = true` | `SecurityHeadersMiddleware` |
| RDS | `require_secure_transport = 1` | n/a |

**HSTS** tells a browser to refuse plain HTTP to a host for two years. Sent only
in production — locally it would make the browser refuse `http://localhost`,
which is hard to undo and breaks every other project on your machine.

Add HSTS to Hostinger too, once you are confident HTTPS works everywhere:

```apache
Header always set Strict-Transport-Security "max-age=63072000; includeSubDomains"
```

**Be sure before you add it.** A browser that has seen this header will refuse
plain HTTP to your domain for two years, and there is no way to tell it
otherwise.

Verify everything at <https://securityheaders.com> and
<https://www.ssllabs.com/ssltest/>. Aim for A or better on both.

---

## Deployment order, and what to check between steps

Each tier depends on the one before. Doing them in this order means each
failure is diagnosable in isolation.

### 1. Database (AWS RDS)

**Verify:** migrations applied, 13 tables and 13 procedures present, the
application user exists and cannot `DROP`.

### 2. Backend (Fly.io)

**Verify:** `/health` returns ok; `/health/ready` returns **an empty
`warnings` list**; `fly logs` shows `application_started`; the database is
reachable from `fly ssh console`.

**Do not continue while `warnings` is non-empty.** Every entry names something
that must be fixed.

### 3. Frontend (Hostinger)

**Verify:** the site loads over HTTPS; a deep link like `/settings` does not
404; `config.json` shows the real API address; creating a campaign **succeeds**
(a 403 here means the cookie domain is wrong).

### 4. Cloudflare

Last, so that if something breaks you know it was Cloudflare. See
[CLOUDFLARE_WAF_PROMPT.md](../CLOUDFLARE_WAF_PROMPT.md).

**Verify:** the site still works; requests carry `CF-Ray` headers; the analytics
country field starts populating.

### The end-to-end check

Play one turn. Then confirm from the logs:

```bash
fly logs --no-tail | grep gemini_call_completed
```

You should see the model, latency and token counts — **and no prompt or reply
content anywhere in the log.** That last part is the whole design working.

---

## Rollback

| Tier | How | Time |
|---|---|---|
| Frontend | Re-upload the zip you took before deploying | under a minute |
| Backend | `fly releases`, then `fly deploy --image <previous>` | 1–2 minutes |
| Database | **Migrations do not roll back.** Write a new migration that reverses the change | varies |
| Cloudflare | Pause the site, or disable the rule you added | seconds |

**Two things worth internalising:**

**Take the frontend zip before every upload.** It takes ten seconds and is the
difference between a one-minute rollback and rebuilding from Git under
pressure.

**Databases move forward only.** This is why the expand-and-contract pattern
exists — see
[DATABASE_OPERATIONS.md](../backend/docs/DATABASE_OPERATIONS.md). Never write a
migration that drops a column the current code still reads, because then the
rollback is impossible rather than merely awkward.

**Practise a rollback before you need one.** Deploy twice, roll back, confirm
the earlier version returns. Ten minutes now buys a much better afternoon
later.

---

## Related documents

- [Fly.io](DEPLOY_PYTHON_FLYIO.md) · [Hostinger](DEPLOY_ANGULAR_HOSTINGER.md) ·
  [RDS](DEPLOY_MYSQL_RDS.md) · [Cross-cloud](DEPLOY_CROSS_CLOUD.md)
- [Costs](COSTS.md) · [Cloudflare prompt](../CLOUDFLARE_WAF_PROMPT.md)
