# Deploying the Angular App to Hostinger

**Read this when** you are putting the frontend on the internet. Do this
**second**, after the backend, so you have its address to point at.

Everything here is written but **not yet performed** — no part of this project
has been deployed. Treat it as a careful plan rather than a transcript.

---

## What you are deploying

`npm run build` produces plain files: HTML, CSS, JavaScript and images. No
program runs on the server. Hostinger simply hands the files over, which is why
this tier is enough and why Server-Side Rendering must stay off.

---

## Step 1 — Point the app at your backend

Before building, edit `frontend/public/config.json`:

```json
{
  "apiBaseUrl": "https://api.yourdomain.com",
  "environment": "production"
}
```

**No trailing slash.** **`https`, not `http`.**

> **The one thing most likely to break your deployment.** The API must be on a
> subdomain of the **same parent domain** as the frontend:
>
> ```
> frontend   https://app.yourdomain.com
> backend    https://api.yourdomain.com     ← same yourdomain.com
> ```
>
> A browser will not let a page read a cookie set by an unrelated domain. If
> the backend stays on `*.fly.dev`, the frontend can never read the
> cross-site request forgery token, and **every save will fail with a 403**.
> Locally this is invisible because both are `localhost`. See
> [backend/docs/SECURITY.md](../backend/docs/SECURITY.md).

This file is read at runtime, so you can change it on the server later without
rebuilding.

---

## Step 2 — Build

```bash
cd frontend && npm run build
```

**Expect:** a table of chunk sizes and
`Output location: .../dist/ai-dungeon-master`.

**The files you need are in `dist/ai-dungeon-master/browser/`.** Note the
`browser` subfolder — uploading the level above it is the most common mistake
here, and produces a blank page.

```bash
ls dist/ai-dungeon-master/browser/
# index.html  config.json  main-*.js  styles-*.css  chunk-*.js  favicon.ico
```

**If `npm run build` fails with a type error:** the build is stricter than the
development server. Fix the error; do not disable the check.

---

## Step 3 — Upload

### Via hPanel's file manager

1. Sign in at <https://hpanel.hostinger.com>.
2. **Websites** in the top navigation, then **Manage** beside your domain.
3. In the left sidebar find **Files → File Manager**.
4. You land in `/home/uXXXXXXX/`. Open **`public_html`** — this is the folder
   the web server actually serves.
5. **Delete what is already there** if this is a fresh site (Hostinger puts a
   placeholder `index.html` in it). Select all, then the bin icon.
6. Click **Upload Files** (top right).
7. Upload **the contents** of `dist/ai-dungeon-master/browser/`, not the folder
   itself. You want `public_html/index.html`, **not**
   `public_html/browser/index.html`.

**Tip:** zip the contents locally, upload the one zip, then use the file
manager's **Extract** option. Far quicker than dozens of individual files.

### Via FTP

FTP (File Transfer Protocol) copies files to a server. Use FileZilla, free from
<https://filezilla-project.org>.

Credentials are in hPanel under **Files → FTP Accounts**.

| Field | Value |
|---|---|
| Host | Shown in hPanel, e.g. `ftp.yourdomain.com` |
| Username | Shown in hPanel, usually like `u123456789` |
| Password | The one you set |
| Port | `21` for FTP, or `22` if SFTP is offered |

**Choose SFTP if it is offered.** Plain FTP sends your password unencrypted.

Connect, navigate to `public_html` on the right, drag the contents of
`browser/` across.

---

## Step 4 — The rewrite rule (do not skip this)

**This catches nearly everyone the first time.**

### The problem

Your app has addresses like `/campaigns` and `/settings`. Those are not files —
there is no `campaigns.html` on the server. Angular creates them in the browser
after `index.html` loads.

So this works:

1. Visit `yourdomain.com` → server sends `index.html` → Angular starts →
   clicking "Campaigns" changes the address to `/campaigns`. Fine.

And this breaks:

2. Press **refresh** on `/campaigns`. The browser asks the server for
   `/campaigns`. There is no such file. **404.**

Same for anyone opening a bookmark or a shared link.

### The fix

Tell the server: if the requested path is not a real file, send `index.html`
anyway and let Angular work it out.

Create a file named exactly **`.htaccess`** (with the leading dot) inside
`public_html`:

```apache
<IfModule mod_rewrite.c>
  RewriteEngine On
  RewriteBase /

  # If the request is for a file or folder that exists, serve it normally.
  RewriteCond %{REQUEST_FILENAME} -f [OR]
  RewriteCond %{REQUEST_FILENAME} -d
  RewriteRule ^ - [L]

  # Otherwise hand over index.html and let Angular route it.
  RewriteRule ^ index.html [L]
</IfModule>

# Never cache index.html or config.json. Both must be re-fetched every time,
# or a returning visitor keeps loading the previous release — and, worse, keeps
# talking to the previous backend address.
<FilesMatch "^(index\.html|config\.json)$">
  <IfModule mod_headers.c>
    Header set Cache-Control "no-cache, no-store, must-revalidate"
  </IfModule>
</FilesMatch>

# Cache the fingerprinted assets for a year. Their names change with their
# contents, so a stale one can never be served for new content.
<FilesMatch "\.(js|css|woff2|png|svg|ico)$">
  <IfModule mod_headers.c>
    Header set Cache-Control "public, max-age=31536000, immutable"
  </IfModule>
</FilesMatch>

<IfModule mod_headers.c>
  Header always set X-Content-Type-Options "nosniff"
  Header always set X-Frame-Options "DENY"
  Header always set Referrer-Policy "strict-origin-when-cross-origin"
  Header always set Permissions-Policy "geolocation=(), camera=(), payment=()"
</IfModule>
```

**Creating it in the file manager:** the file manager may hide dotfiles. Use
**New File**, name it `.htaccess`, and if it disappears, look for a "show
hidden files" toggle in the settings menu.

**Verify it worked:** visit `https://app.yourdomain.com/settings` directly. You
should get the settings screen, not a 404.

**Note the microphone caveat.** Browsers only allow microphone access on HTTPS.
If voice works locally and not on the deployed site, check the site is on
HTTPS — that is the answer nine times out of ten.

---

## Step 5 — Point the domain

### If the domain is registered with Hostinger

Mostly done. In hPanel, **Domains → Manage**, confirm it points at this hosting
account. To use `app.yourdomain.com` rather than the bare domain, create a
subdomain under **Domains → Subdomains** — note that this creates a *different*
folder, such as `public_html/app`, and your files must go there instead.

### If the domain is registered elsewhere

In hPanel find your nameservers (usually `ns1.dns-parking.com` and
`ns2.dns-parking.com`), then set them at your registrar.

**DNS changes take up to 48 hours**, though usually under an hour. Check
progress at <https://dnschecker.org>.

### TLS

Hostinger issues a free Let's Encrypt certificate. In hPanel, **Security → SSL**,
and enable **Force HTTPS**.

**Wait for DNS to finish first.** Issuing a certificate before the domain
resolves to Hostinger fails, and the error is not obvious.

---

## Step 6 — Verify, in this order

1. **`https://app.yourdomain.com` loads**, padlock shown.
2. **Deep links work.** Go straight to `/settings`. Not a 404.
3. **The config is correct.** Open `https://app.yourdomain.com/config.json` —
   it should show your real API address, not `localhost`.
4. **The API is reachable.** Open the browser's developer tools (F12), the
   **Network** tab, and reload. Requests to `api.yourdomain.com` should return
   200, not red.
5. **Saving works.** Create a campaign. **If this fails with 403, the cookie
   domain is wrong** — go back to the warning in Step 1.
6. **Voice works**, if you enabled it. Requires HTTPS.

---

## Updating later

```bash
cd frontend && npm run build
```

Upload the contents of `browser/` again, overwriting.

**Do not delete `.htaccess`** — it is not part of the build output and will not
be replaced. If deep links suddenly 404 after an update, this is why.

`config.json` is overwritten by each upload, so keep your production copy safe
or re-edit it after uploading. `public/config.production.example.json` exists as
a reminder.

---

## Rollback

Static files make this simple, if you prepare:

1. **Before uploading, download the current `public_html` as a zip.** Name it
   with the date.
2. To roll back, delete the contents and upload that zip.

Rollback is under a minute, and needs no cooperation from anyone.

For anything beyond an occasional release, put `frontend/` in its own Git
repository and let Hostinger's Git deployment handle it — then a rollback is
`git revert`.

---

## When it goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| Blank white page | Uploaded the wrong folder level | Upload the contents of `browser/` |
| Blank page, console says `config.json` 404 | It was not uploaded | Confirm it sits beside `index.html` |
| Refresh gives 404 | No `.htaccess` | Step 4 |
| Works, but no data | Backend not reachable | Check `config.json`, and that the backend is up |
| CORS error in console | Backend does not list this origin | Set `CORS_ALLOWED_ORIGINS` on Fly |
| Every save gives 403 | Cookie domain mismatch | The Step 1 warning |
| Microphone does nothing | Not on HTTPS | Enable Force HTTPS |
| Old version still showing | `index.html` was cached | The cache rules in Step 4; hard-refresh with Ctrl+Shift+R |

---

## Related documents

- [Backend deployment](DEPLOY_PYTHON_FLYIO.md) — do this first.
- [Cross-cutting concerns](DEPLOY_CROSS_CUTTING.md) — CORS, TLS, headers.
- [Costs](COSTS.md).
