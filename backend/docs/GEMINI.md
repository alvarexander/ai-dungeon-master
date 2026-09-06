# Google Gemini — Getting a Key, and What the Free Tier Gives You

**Read this when** you need an API key for the first time, when the Dungeon
Master stops replying, or when you want to know what Google does with the words
your players type. It assumes you have never used a developer console before
and describes what each page looks like.

---

## Part 1 — Getting your API key

### What an API key is

A long random string that identifies your account to Google. **Treat it exactly
like a house key.** Anyone holding it can use your allowance and, if you ever
add a payment method, spend your money. It is not a password you can change
your mind about later — if it leaks, you revoke it and issue a new one.

### The steps

1. **Open <https://aistudio.google.com/apikey> in your browser.**

   *What you will see:* a page headed **Google AI Studio** with a dark
   navigation strip down the left. The main area is titled **API keys** and, if
   you have never made one, is mostly empty with a short explanatory paragraph.

2. **Sign in with a Google account** if you are not already. Any personal
   Google account works. You do not need a paid plan and you do not need to
   enter a payment card.

3. **Accept the terms** if you are prompted. A dialogue appears the first time,
   with checkboxes about the Google APIs Terms of Service. You must accept to
   continue. Part 3 of this document explains what you are agreeing to
   regarding your data — it is worth reading before you tick.

4. **Find the blue button labelled `Create API key`.** It sits in the upper
   right of the main panel, or in the centre of the empty state if you have no
   keys yet.

5. **Click it.** A dialogue asks which Google Cloud project to attach the key
   to. If you have never used Google Cloud, there will be an option along the
   lines of **Create API key in new project** — choose that. You do not need to
   understand Google Cloud projects; this is just a folder Google files the key
   under.

6. **Copy the key.** It appears in a box, looking something like
   `AIzaSy...your-actual-key-here...`. There is a copy icon beside it.

   **Copy it now.** Depending on the page version, you may not be shown the
   full key again — you would have to delete it and make another. No harm done
   if that happens, but it is a wasted five minutes.

7. **Paste it into your configuration file.** Open
   `~/Git/ai-dungeon-master/backend/.env` in any text editor and find this line:

   ```
   GEMINI_API_KEY=CHANGE_ME_paste_your_key_here
   ```

   Replace everything after the `=` with your key. No quotation marks, no
   spaces around the `=`, nothing after the key. It should end up looking like:

   ```
   GEMINI_API_KEY=AIzaSy...your-actual-key-here...
   ```

8. **Save the file.**

### Check it worked

```bash
cd ~/Git/ai-dungeon-master/backend && uv run python scripts/check_gemini_models.py
```

**What this does:** asks Google which models your key is allowed to use, and
compares that list against the model this application is configured for.

**What you should see:** a list of model names, one marked
`<-- currently configured in .env`, and a closing line confirming your model is
available.

**Common failures:**

| Message | Cause | Fix |
|---|---|---|
| `GEMINI_API_KEY is not set` | The file was not saved, or still holds the placeholder | Redo steps 7 and 8 |
| `Google refused the request (HTTP 400)` | The key was copied incompletely | Copy it again, whole |
| `HTTP 403` | The key was revoked, or its project has the API disabled | Create a fresh key |
| `Could not reach Google` | No internet connection | Check your connection |
| `'gemini-3.5-flash' is NOT in the list` | Your account cannot use that model | Set `GEMINI_MODEL_ID` in `.env` to a name the script suggested |

---

## Part 2 — Keeping the key safe

**The single most important rule: the key never reaches the browser.**

Every call to Gemini happens on the backend server. There is no configuration
setting in the Angular application that accepts a key, because a key in a web
page is a key given to everybody — anyone can open the browser's developer
tools and read it. This is why the application is built as two programs rather
than one.

The rest, in order of how often people get caught out:

- **`.env` is never committed.** It is already listed in `.gitignore`. Verify
  with `git status` — if you ever see `.env` in the list of changes, stop and
  fix it before committing.
- **Never paste it into a chat message, a bug report, or a screenshot.** This
  is the most common way keys leak in practice.
- **Never put it in a URL.** URLs are recorded in server logs, browser history
  and proxy logs. This application sends the key in an HTTP header, which is
  not recorded that way.
- **If it leaks, revoke it.** Go back to the API keys page, delete the key, and
  create a new one. Deleting takes effect immediately.
- **In production it is not in a file at all.** It is stored with
  `fly secrets set`, which keeps it encrypted and injects it into the running
  container. See [the deployment guide](../../docs/DEPLOY_PYTHON_FLYIO.md).

---

## Part 3 — What Google does with your players' words

**This section matters more than the rest.** Read it before you let anyone else
use the application.

### The answer, stated plainly

**On the free tier, Google uses what you send to improve its products, and
human reviewers may read it.**

Google's API terms are explicit. For the unpaid service, they state that Google
uses submitted content and generated responses "to provide, improve, and
develop Google products and services", and that "human reviewers may read,
annotate, and process your API input and output". Google says it disconnects
that data from your account and API key before human review, and advises: *do
not submit sensitive, confidential, or personal information* to the unpaid
service.

**On the paid tier this changes completely.** Google states it does not use
paid-tier prompts or responses to improve its products, and retains them only
briefly for abuse detection.

### Why this is a real problem for this application

Players type their own names. They type their friends' names. They describe
where they live, what happened at work, in-jokes that identify them. A campaign
transcript is personal data, which is exactly why the database encrypts it.

But encryption at rest protects data sitting in a database. It does nothing
about data you deliberately send to somebody else. The prompt is the one place
where personal data leaves your control by design.

### What this application does about it

Three things, and it is worth being honest that only the third is complete.

1. **Outbound scrubbing.** Before any prompt leaves the server, text that looks
   like personal data is replaced — email addresses, phone numbers, card-shaped
   digit strings, postcodes, web links, dates of birth. The code is
   [`app/services/scrubber.py`](../app/services/scrubber.py) and it is on by
   default (`SCRUB_OUTBOUND_PROMPTS=true`).

   **What it cannot do:** catch "my sister Emma is coming over", because that
   is indistinguishable from a player naming a character. An early version
   stripped every capitalised word and made the Dungeon Master incoherent — a
   privacy control that ruins the product gets switched off, and a control
   that is switched off protects nobody. So it handles structured patterns
   only. It reduces accidental disclosure; it does not close the channel.

2. **In-app disclosure.** The interface tells players, in plain language and
   before they type, that their messages are sent to Google and that on the
   free tier Google may use them for training. People cannot make a sensible
   choice about what to type if they do not know where it goes.

3. **The complete fix: enable billing.** Adding a payment method moves you to
   the paid tier, whose terms forbid training on your prompts. At the traffic
   this application will see, the actual cost is pennies per month. **If real
   people other than you ever use this, do this.** It is the only measure here
   that fully solves the problem rather than reducing it.

---

## Part 4 — The free tier's limits

### Google no longer publishes the numbers

This is worth knowing, because it is a change from how things used to work.
Google's rate-limits documentation now says limits "depend on a variety of
factors (such as your usage tier)" and directs you to look them up for your own
account. There is no published table to quote.

**Your actual limits are shown at <https://aistudio.google.com/rate-limit>.**

For rough orientation, free-tier limits for a Flash model have commonly sat
around **10 requests per minute** and **250 requests per day**, with a
generous per-minute token allowance. Treat those as the shape of the thing, not
as a promise — check your dashboard for the real numbers, and expect them to
change without notice.

### What this means in practice

A conversational turn is one request. So a daily limit in the low hundreds is
**a few hours of solo play per day** — comfortable for you building and testing,
and not enough for a group of friends using it heavily.

### What the application does when it hits a limit

It does not crash and it does not show a stack trace.

1. Gemini returns HTTP 429.
2. The client retries with **exponential backoff and jitter** — waiting longer
   after each failure, with a small random variation so that many clients
   failing together do not all retry in lockstep and recreate the overload.
3. If retries are exhausted, it raises a specific error rather than a generic
   one, and the player sees:

   > The Dungeon Master needs a moment — the free AI allowance has been used
   > up. Per-minute limits clear within about a minute; if this persists, the
   > daily allowance is spent and will reset tomorrow.

4. A `quota_exhausted` analytics event is recorded — a pseudonymous count with
   no free text — so you can see how often this happens without inspecting
   anybody's session.

### Seeing it coming

Every AI call is logged with its token counts, latency and finish reason (never
its content). In Phase 2 the same data lands in the `gemini_calls` table, and
[this query](DATABASE_OPERATIONS.md) shows quota pressure by day.

---

## Part 5 — Which model, and why

The default is **`gemini-3.5-flash`**, set in `.env` as `GEMINI_MODEL_ID`.

**Why this one.** It is a stable release, not a preview, so it will not be
withdrawn underneath you. Google lists it as free-tier eligible. And it is
described for routine, high-throughput work — which is exactly the shape of a
chat loop that fires on every single turn a player takes.

**Alternatives, if you want to change it.** Edit the one line in `.env`; no
code changes anywhere.

| Model | When to use it |
|---|---|
| `gemini-3.5-flash` | The default. Balanced. |
| `gemini-3.5-flash-lite` | If you are hitting quota limits. Faster and cheaper; prose is a little plainer. |
| `gemini-3.6-flash` | Newer. Try it if narration quality matters more than quota headroom. |
| `gemini-2.5-flash` | Older, well-proven. A fallback if a newer model misbehaves. |

Always confirm your choice with `scripts/check_gemini_models.py` before
restarting — a model name your key cannot reach produces a 404, which the
application reports with a message pointing you back at that script.

---

## Part 6 — How the Dungeon Master is instructed

The standing instruction that turns a general-purpose model into a Dungeon
Master lives in
[`app/services/dungeon_master.py`](../app/services/dungeon_master.py), in
`DM_SYSTEM_PROMPT`. It is plain English and you are meant to edit it — it is
the main lever on how the game *feels*.

It covers four things: how to narrate (second person, present tense, two to
four paragraphs, always hand control back), how to handle rules (call for
checks by name, keep the arithmetic light, never let a failure stop the story),
how to treat the player (say "yes, and" or "yes, but", never a flat no), and
what never to do (never break character, never claim real-world facts).

Three settings are appended to it at request time, from the campaign and the
player's preferences: **tone** (heroic, gritty, comedic, horror, mystery),
**length** (brief, standard, rich) and **content filter** (family, standard,
mature). Each is a specific instruction rather than a vague adjective, because
vague adjectives produce vague changes.

Only the last twenty messages travel with each turn, with the campaign premise
restated every time so the story's thread is never lost when older messages
fall out of the window. That keeps each request affordable in tokens.

---

## Related documents

- [SECURITY.md](SECURITY.md) — how secrets are handled throughout.
- [OBSERVABILITY.md](OBSERVABILITY.md) — what is logged about each AI call, and
  the opt-in flag for capturing prompt content.
- [ADR-008](../../docs/DECISIONS_PRIVACY.md) — why voice audio does not go to
  Google even though the text does.
- [RUNNING.md](../../RUNNING.md) — starting the application.
