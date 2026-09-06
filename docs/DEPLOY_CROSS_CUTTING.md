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

## Secrets in production

Two, and only two:

| Secret | Set with |
|---|---|
| `GEMINI_API_KEY` | `fly secrets set GEMINI_API_KEY="..."` |
| `DATABASE_URL` (contains the password) | `fly secrets set DATABASE_URL="..."` |

```bash
fly secrets set GEMINI_API_KEY="your-real-key"
fly secrets set DATABASE_URL="mysql+aiomysql://dm:PASSWORD@host:3306/dungeon_master?ssl=true"
fly secrets list      # names and digests only, never values
```

**Why this rather than putting them in `fly.toml`.** That file is committed to
version control, and Git history is permanent and frequently made public later.
A secret that has been committed must be treated as leaked and rotated, not
merely deleted from the current version.

Setting a secret restarts the application, so the new value takes effect
immediately.

**If a secret does leak:** rotate it rather than hoping. Generate a new Gemini
key and delete the old one at <https://aistudio.google.com/apikey>; change the
database password and update the secret. Both take about two minutes, and both
are far cheaper than the alternative.

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
[DATABASE.md](../backend/docs/DATABASE.md). Never write a
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
