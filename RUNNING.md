# How to Run This On Your Machine

**Read this when** you want to start the application locally — either for the
first time, or to get going again after a restart. It assumes you have never
run a development server before and explains what each command does, what you
should see when it works, and what the common failures look like.

For what the project *is*, read [README.md](README.md). For how it is built,
read [SYSTEM_GUIDE.md](SYSTEM_GUIDE.md).

---

## Before you start: the shape of what you are running

This application is **two programs running at the same time**, in two separate
terminal windows.

| | What it is | Where it runs |
|---|---|---|
| **Backend** | A Python program that talks to Google's AI, holds the game rules, and encrypts everything | `http://127.0.0.1:8000` |
| **Frontend** | The web page you actually look at and type into | `http://localhost:4200` |

They are separate on purpose, because in production they will live with two
different hosting companies. Running them separately on your laptop means you
find out today about anything that only breaks when they are apart.

`127.0.0.1` and `localhost` both mean "this computer". Nothing is exposed to
the internet; nobody else can reach either address.

---

## Part 1 — One-time setup

You do this once, ever.

### Step 1. Check you have the tools

Open the Terminal application and run:

```bash
uv --version && node --version
```

**What you should see:** two version numbers, something like `uv 0.12.8` and
`v24.20.0`.

**If you see `command not found: uv`:** the Python tool manager is not
installed. Install it with:

```bash
brew install uv
```

**If you see `command not found: node`:** install it with `brew install node`.

*(What these are: `uv` installs and manages Python and its libraries. `node` is
the toolchain that builds the web page. Neither is part of the running product
— they are the workshop, not the furniture.)*

### Step 2. Install the backend's libraries

```bash
cd ~/Git/ai-dungeon-master/backend && uv sync --extra voice
```

**What this does:** downloads the roughly twenty libraries the backend needs
into a private folder called `.venv`, so they never collide with anything else
on your machine. `--extra voice` additionally downloads the speech-to-text
model libraries.

**What you should see:** a list of packages being resolved and installed,
ending in something like `Installed 47 packages in 2.3s`.

**How long:** the first run takes a few minutes, mostly because the voice
libraries are several hundred megabytes. Later runs take seconds.

**If it fails on the voice libraries:** drop them and carry on — typing works
perfectly without voice input:

```bash
cd ~/Git/ai-dungeon-master/backend && uv sync
```

The voice button will then show a clear message explaining it is unavailable,
rather than breaking anything.

### Step 3. Create your private configuration file

```bash
cd ~/Git/ai-dungeon-master/backend && cp .env.example .env
```

**What this does:** `.env.example` is the blank form, shared with everyone.
`.env` is your filled-in copy, which stays on your machine and is never
committed. This command makes your copy.

**What you should see:** nothing at all. On the command line, silence means
success.

### Step 4. Put your Google AI key into it

Everything except the AI replies works without this, so you can skip it and
come back. But the Dungeon Master will not answer until it is done.

Full step-by-step instructions, with descriptions of what each page looks like,
are in [backend/docs/GEMINI.md](backend/docs/GEMINI.md). The short version:

1. Go to <https://aistudio.google.com/apikey> and sign in with a Google account.
2. Click **Create API key**.
3. Copy the long string it shows you.
4. Open `~/Git/ai-dungeon-master/backend/.env` in a text editor.
5. Find the line `GEMINI_API_KEY=CHANGE_ME_paste_your_key_here` and replace
   everything after the `=` with your key. No quotes, no spaces.
6. Save the file.

**Treat that key like a house key.** Anyone holding it can use your Google
allowance. It goes in `.env` and nowhere else — never in a message, never in a
screenshot, never in a file you commit.

To check it worked:

```bash
cd ~/Git/ai-dungeon-master/backend && uv run python scripts/check_gemini_models.py
```

**What you should see:** a list of model names, with `gemini-3.5-flash` marked
as the one you have configured, and a final line saying your model is
available.

**If you see `GEMINI_API_KEY is not set`:** step 4 did not save, or the key is
still the placeholder text.

**If you see `Google refused the request (HTTP 400)`:** the key was copied
incompletely. Generate a fresh one and paste it again.

### Step 5. Install the frontend's libraries

```bash
cd ~/Git/ai-dungeon-master/frontend && npm install
```

**What you should see:** a progress display, then a summary like
`added 812 packages in 25s`. Warnings about deprecated sub-dependencies are
normal and can be ignored.

---

## Part 2 — Starting the application

You do this every time. **You need two terminal windows**, because each program
keeps running and holds onto its window.

### Terminal 1 — the backend

```bash
cd ~/Git/ai-dungeon-master/backend && uv run uvicorn app.main:app --reload --port 8000
```

**What you should see**, in this order:

1. A large warning box reading `DEVELOPMENT MODE — NOT SECURE`, listing three
   things: development encryption key, stubbed authentication, in-memory
   storage. **This is correct.** It is the application telling you honestly
   that it is not protecting anything real yet. It refuses to start with these
   settings if you ever mark it as production.
2. A line like `demo_user_created`.
3. `Uvicorn running on http://127.0.0.1:8000`.

Leave this window alone. It is now the server.

*(`--reload` means it watches the files and restarts itself whenever one
changes, so you rarely need to stop and start it by hand.)*

### Terminal 2 — the frontend

Open a **second** terminal window (Cmd+N in Terminal) and run:

```bash
cd ~/Git/ai-dungeon-master/frontend && npm start
```

**What you should see:** a build progress display, then:

```
Watch mode enabled. Watching for file changes...
  ➜  Local:   http://localhost:4200/
```

The first build takes 15–30 seconds. Later rebuilds are near-instant.

### Then open the application

Go to **<http://localhost:4200>** in your browser.

---

## Running it from PyCharm instead of the terminal

If you would rather press a green ▶ button than type commands, PyCharm needs a
"run configuration" — a saved set of instructions telling it what to start.

The thing that trips people up: **uvicorn is a module, not a script.** PyCharm's
dialogue defaults to "script" and then complains `Please specify a script name`,
because there is no script file to point at.

### The backend

1. **Run → Edit Configurations…**, then click **+** and choose **Python**.
2. **Name:** `Backend (uvicorn)`
3. **Interpreter:** choose the one ending `backend/.venv`. PyCharm usually
   finds it on its own. If it is not offered, add it manually from
   `~/Git/ai-dungeon-master/backend/.venv/bin/python`.
4. **Change the `script` dropdown to `module`.** This is the step that fixes
   the "specify a script name" error.
5. In the box beside it, type: `uvicorn`
6. **Script parameters:**
   ```
   app.main:app --reload --port 8000
   ```
7. **Working directory:** `~/Git/ai-dungeon-master/backend`

   Do not skip this. The application reads its `.env` file relative to wherever
   it starts, so a wrong working directory produces
   `CORS_ALLOWED_ORIGINS is empty` and it refuses to boot.
8. **Environment variables:** leave `PYTHONUNBUFFERED=1`. It makes log output
   appear immediately instead of in batches.
9. **Paths to ".env" files:** leave blank. The application loads `.env` itself.
10. **Remove the `Run with uv run` chip** if it is present — click the small
    `×` on it. The interpreter already points at the virtual environment that
    has uvicorn in it, so going through `uv` again is redundant.
11. **Apply**, then **OK**.

**What you should see when you press ▶:** the `DEVELOPMENT MODE — NOT SECURE`
warning box, then `Uvicorn running on http://127.0.0.1:8000`.

**To debug:** press the bug icon rather than ▶ and PyCharm will stop at
breakpoints. If breakpoints seem to be ignored, remove `--reload` from the
parameters — the auto-restarting file watcher and the debugger interfere with
each other.

### The tests

1. **+** → **Python tests** → **pytest**
2. **Name:** `Backend tests`
3. **Working directory:** `~/Git/ai-dungeon-master/backend`
4. Leave everything else alone.

Pressing ▶ runs all 88 and shows them as a pass/fail tree.

### The frontend

PyCharm Professional can run the Angular server too, though the terminal is
simpler here:

1. **+** → **npm**
2. **package.json:** `~/Git/ai-dungeon-master/frontend/package.json`
3. **Command:** `run`, **Scripts:** `start`


---

## The one-command alternative: Docker

Everything above installs Python and Node on your machine. If you would rather
not, **Docker** runs both programs in isolated packages called containers, with
nothing installed but Docker itself.

Install Docker Desktop from <https://www.docker.com/products/docker-desktop/>.

### First run

```bash
cd ~/Git/ai-dungeon-master && cp backend/.env.example backend/.env
```

Paste your Gemini key into `backend/.env` (Step 4 above explains how to get
one), then:

```bash
cd ~/Git/ai-dungeon-master && docker compose up --build
```

**What you should see:** a long build — five to ten minutes the first time,
mostly downloading Python, Node and the speech model — then log lines from both
`dungeon-master-api` and `dungeon-master-web`.

Then open **<http://localhost:4200>** exactly as before.

**Afterwards** the images are cached and `docker compose up` starts in seconds.

### Everyday commands

```bash
docker compose up            # start both
docker compose down          # stop both
docker compose logs -f api   # watch the backend
docker compose up --build    # rebuild after changing dependencies
```

### Which should you use?

| | Local install | Docker |
|---|---|---|
| First-time setup | Several steps | One command, after installing Docker |
| Code changes appear | Instantly, both tiers | Needs a rebuild |
| Debugging in PyCharm | Straightforward | More setup |
| Matches production | Close | Closer, for the backend |

**Use the local install while writing code** — `--reload` and `npm start` pick
up changes as you save them, which Docker does not. **Use Docker** to check
that a change works in a clean environment, or to run the whole thing without
installing anything.

### Honest caveat

The container images are written but have **not been built and run** — Docker
was not installed on the machine where this project was created. Expect one or
two small corrections on your first `docker compose up --build`. The
application itself is verified working; it is the packaging that is unproven.


---

## Part 3 — Checking it works

### The backend on its own

With the backend running, open **<http://127.0.0.1:8000/docs>**.

This is the Swagger page — an automatically generated, browsable list of every
address the backend answers on, what each one accepts, and what it returns.
Every endpoint has a **Try it out** button that sends a real request. It is
generated from the code itself, so it can never drift out of date.

Two useful addresses:

- **<http://127.0.0.1:8000/health>** — should show `{"status":"ok"}`. If this
  works, the server is alive.
- **<http://127.0.0.1:8000/health/ready>** — shows the configuration and a
  `warnings` list. `"gemini_key_configured": true` confirms step 4 worked.

### The whole thing together

In the browser at `http://localhost:4200`, type something into the chat box —
`I push open the chapel door and hold up the lantern` — and send it. Within a
few seconds the Dungeon Master should narrate what happens next.

---

## Optional: fill it with example data

```bash
cd ~/Git/ai-dungeon-master/backend && uv run python scripts/seed_dev_data.py
```

Creates three example accounts, each with a campaign and a character. Every
name is invented by a fake-data generator and belongs to nobody. Run it with
the backend already running, in a third terminal.

---

## Stopping everything

Press **Ctrl+C** in each terminal window. That is the standard way to stop a
running program on the command line.

**Everything you created is now gone.** Phase 1 keeps all data in the server's
memory rather than in a database, so campaigns, characters and conversations
disappear on restart. This is expected — the database is Phase 2. The seed
script above gets you back to a populated state in one command.

---

## When something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| `command not found: uv` | The Python tool manager is missing | `brew install uv` |
| `command not found: npm` | Node is missing | `brew install node` |
| `Address already in use` | Something is already on that port — usually a copy of the server you forgot to stop | Find it with `lsof -ti:8000` then stop it with `kill $(lsof -ti:8000)`. Or start on another port with `--port 8001` |
| `CORS_ALLOWED_ORIGINS is empty` at startup | Step 3 was skipped, so there is no `.env` file | Run step 3 |
| Red `Failed to fetch` in the browser | The backend is not running | Check Terminal 1 is still going |
| Dungeon Master says the AI credentials were rejected | The Gemini key is wrong or missing | Redo step 4, then run the check script |
| Dungeon Master says the free allowance is used up | You have hit Google's per-minute or per-day limit | Wait a minute. If it persists, the daily limit is spent and resets tomorrow. See [backend/docs/GEMINI.md](backend/docs/GEMINI.md) |
| Voice button says speech-to-text is unavailable | The optional voice libraries are not installed | `cd backend && uv sync --extra voice`, then restart the backend |
| A page reloads and shows a 403 error | The cross-site request forgery token was lost | Reload the page. If it repeats, restart both programs |

**Whatever goes wrong, look for the correlation ID.** Every error the
application produces carries a random identifier, shown on screen and returned
in the `X-Correlation-ID` header. Search Terminal 1 for that string and you
will find every log line for that exact request. That is the intended way to
debug this application — it is designed so that you never need to read a user's
data to find out what happened to them.

---

## Running the tests

```bash
cd ~/Git/ai-dungeon-master/backend && uv run pytest
```

**What you should see:** a row of dots and a final line like `88 passed in
2.2s`. These tests cover the encryption, the log redaction filter, the SSRF
guard, rate limiting, and the API's security behaviour. If they pass, the
privacy machinery is genuinely working rather than merely described.

```bash
cd ~/Git/ai-dungeon-master/frontend && npm test
```

---

## Related documents

- [README.md](README.md) — what this project is.
- [SYSTEM_GUIDE.md](SYSTEM_GUIDE.md) — how the pieces fit together, and how to
  deploy them.
- [backend/docs/GEMINI.md](backend/docs/GEMINI.md) — getting an API key, and
  what the free tier allows.
- [docs/GLOSSARY.md](docs/GLOSSARY.md) — every technical term used anywhere in
  this project, defined.
