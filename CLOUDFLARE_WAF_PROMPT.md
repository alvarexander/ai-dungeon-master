# Cloudflare WAF Setup — a self-contained prompt

**Read this when** the application is deployed and you want to put Cloudflare
in front of it.

**How to use this file:** copy everything below the line into a conversation
with an AI assistant that has browser access, fill in the four values marked
`FILL IN`, and follow along. It assumes no knowledge of this project and no
prior conversation, so it works as a standalone brief.

---

## PROMPT BEGINS HERE

I need help configuring Cloudflare for a small web application I have just
deployed. **I have never used Cloudflare before and I am not a programmer**, so
please explain what each setting does before we change it, and tell me what I
should expect to see on screen at each step.

### My details

- Cloudflare account email: `FILL IN`
- Frontend domain: `FILL IN` — for example `app.mydomain.com`, static files
  hosted on Hostinger
- Backend API domain: `FILL IN` — for example `api.mydomain.com`, a container
  running on Fly.io
- Domain registrar: `FILL IN`

### What the application is

A web application where people play Dungeons & Dragons with an AI Dungeon
Master. Two parts:

1. **The frontend** — plain HTML, CSS and JavaScript on Hostinger. No server
   program. It is a single-page application, so addresses like
   `/campaigns` are created in the browser, not on the server.
2. **The backend** — a Python API on Fly.io. It calls Google Gemini for the AI
   replies and accepts uploaded audio recordings for transcription.

### What I want

**1. DDoS protection** on both domains. A denial-of-service attack floods a
site with traffic until it collapses; Cloudflare absorbs that.

**2. Edge rate limiting** on the API, so abusive traffic is stopped before it
reaches my server and costs me money. My application already rate limits
internally — this is a second, cheaper layer in front of it.

**3. The visitor's country added to requests**, via the `CF-IPCountry` header.
My application uses this so it never has to inspect or store an IP address
itself. This matters to me: I have gone to some trouble to avoid storing IP
addresses, and this header is how I get country-level analytics without them.

**4. Sensible firewall rules** for a small application, without breaking
legitimate users.

**5. To stay on the free plan.** Please tell me if anything you suggest is paid,
and offer the free alternative.

### Important constraints — please respect these

- **Do not enable any feature that modifies my HTML or JavaScript.** Rocket
  Loader, Auto Minify and Email Obfuscation all rewrite the page. My frontend
  is a compiled application and rewriting it can break it in ways that are very
  hard to diagnose.
- **Do not cache API responses.** Everything under `api.` must be
  `Cache Level: Bypass`. Caching them would serve one user's data to another —
  the worst possible failure for this application.
- **Do not enable "I'm Under Attack" mode by default.** It shows an
  interstitial to every visitor.
- **My API accepts file uploads up to 10 MB** (voice recordings). Please make
  sure nothing blocks or truncates those.
- **My API uses cookies for cross-site request forgery protection.** Please do
  not enable anything that strips or rewrites cookies.
- **The frontend needs deep links to work.** Visiting `app.mydomain.com/settings`
  directly must load the app, not 404. My host handles this with a rewrite rule;
  please do not add a Cloudflare rule that interferes.

### Please walk me through, in this order

**Step 1 — Add my domain to Cloudflare.** Explain what changing nameservers
means, what could go wrong, and how long propagation takes. Warn me before
anything takes my site offline, even briefly.

**Step 2 — Check the DNS records came across correctly.** Explain what the
orange cloud (proxied) versus grey cloud (DNS only) means. I want **both**
`app.` and `api.` proxied, and I want to understand what proxying actually
does.

**Step 3 — TLS settings.** Set SSL/TLS mode to **Full (strict)** and explain
why "Flexible" would be a bad idea. Enable **Always Use HTTPS** and **Automatic
HTTPS Rewrites**. Explain HSTS and its risks — I understand it cannot be undone
quickly — and help me decide whether to enable it now or later.

**Step 4 — Caching.** For the frontend, cache the fingerprinted JavaScript and
CSS aggressively, but **never** cache `index.html` or `config.json`, because a
cached copy of either makes returning visitors run an old version. For the API,
bypass the cache entirely.

**Step 5 — Rate limiting on the API.** The free plan allows one rate limiting
rule. Help me pick the most valuable one. My thinking is that the login
endpoint matters most, because that is where password guessing happens — but
tell me if you disagree. Something like:

- Path contains `/api/v1/auth/login`
- More than 10 requests from one address in 1 minute
- Action: block for 10 minutes

Explain how to test that it works without locking myself out.

**Step 6 — Firewall rules.** The free plan allows five custom rules. Please
suggest the five most useful for a small application, and explain the risk of
each. I am considering:

- Block requests to `/.env`, `/.git`, `/wp-admin` and similar. These are pure
  scanner traffic; I run no WordPress.
- Challenge (not block) traffic from countries I have no users in — but please
  warn me about travellers and VPN users before I do this.
- Block known-bad bot scores while allowing search engines.

For each, tell me **what legitimate traffic it could break**.

**Step 7 — Confirm `CF-IPCountry` is arriving.** Show me how to verify the
header actually reaches my backend, using browser developer tools or a `curl`
command.

**Step 8 — Verify nothing broke.** Give me a checklist:

- The frontend loads over HTTPS
- Deep links still work — `app.mydomain.com/settings` does not 404
- The API responds
- Creating something works (this proves cookies and the XSRF token survived
  Cloudflare)
- A voice recording uploads successfully
- Responses carry a `CF-Ray` header, proving traffic is going through
  Cloudflare

**Step 9 — How to turn it off in a hurry.** If something breaks and I cannot
work out why, how do I quickly bypass Cloudflare to confirm whether it is the
cause? Please show me this **before** we finish, so I am not looking it up
under pressure.

### How I would like you to work

- **Explain before changing.** Tell me what a setting does and what could go
  wrong, then do it.
- **Describe the screen.** I do not know where anything is in the Cloudflare
  dashboard — tell me which menu, and whereabouts on the page.
- **Ask me before anything risky**, especially HSTS and anything that could
  take the site offline.
- **Stop and tell me** if something looks wrong rather than working around it.
- **Do not give me a wall of settings to apply blindly.** One thing at a time,
  with a check after each.

## PROMPT ENDS HERE

---

## Notes for you, before you run this

**Do Cloudflare last**, after all three tiers are deployed and verified. If you
add it first and something breaks, you will not know which layer caused it.

**Four things this project specifically needs from Cloudflare:**

1. **`CF-IPCountry`.** The analytics plane reads it for country-level
   geography, which is what lets the application avoid inspecting or storing IP
   addresses at all. See
   [backend/docs/OBSERVABILITY.md](backend/docs/OBSERVABILITY.md).
2. **`CF-Connecting-IP`.** The rate limiter reads this to identify a caller —
   and immediately fingerprints it, never storing the address. Already handled
   in `app/api/deps.py`.
3. **No caching on the API.** Non-negotiable. Cached API responses would serve
   one user's data to another.
4. **Cookies must pass through untouched**, or cross-site request forgery
   protection breaks and nothing saves.

**Cloudflare is a genuine addition, not a replacement.** The application's own
rate limiting stays on — Cloudflare's blocks abusive traffic cheaply at the
edge, and the application's protects against anything that gets past it.

**If the site breaks straight after adding Cloudflare**, set the DNS records to
"DNS only" (the grey cloud). That takes Cloudflare out of the path within a
minute or two and tells you immediately whether it was the cause. Step 9 above
asks the assistant to show you this first, for exactly that reason.
