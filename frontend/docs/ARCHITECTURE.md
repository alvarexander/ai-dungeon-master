# Frontend Architecture

**Read this when** you need the component hierarchy, how state is held, how the
API client works, where XSRF tokens are handled, or why Server-Side Rendering
is off. For the system as a whole, read
[ARCHITECTURE.md](../../ARCHITECTURE.md) at the project root.

---

## Shape of the application

```
main.ts                     fetches config.json, then starts Angular
  app.ts / app.html         the shell: header, navigation, footer
    <router-outlet>         whichever screen matches the address
      features/chat         the play screen        (fully working)
      features/campaigns    list and create        (fully working)
      features/characters   list, create, sheet    (fully working)
      features/settings     preferences            (fully working)
      features/account      profile, deletion      (fully working)
      features/auth         sign in, sign up       (STUBBED, labelled)
```

Everything under `core/` is shared machinery: the API client, the interceptors,
the signal stores, the voice recorder, and the dice.

The dice are worth a note, because they are the clearest example of a pattern
used throughout: `core/dice/dice.ts` holds the rules and `core/dice/polyhedra.ts`
holds the geometry, both as plain functions that know nothing about Angular or
the browser. `features/dice/` turns their output into a spinning die. That
split is what lets the shape of a d20 be tested by a test that renders nothing.

Everything under `shared/ui/` is a reusable piece of interface.

**Feature folders do not import from each other.** If two need the same thing,
it belongs in `core/` or `shared/`.

---

## State: signals, not services with subjects

A **signal** is a value that knows who is reading it. When it changes,
everything that reads it updates — no subscriptions, no manual refreshing, no
wondering whether the screen matches the data.

The pattern used throughout: the writable signal is private, and a read-only
view is exposed.

```typescript
private readonly _lines = signal<ChatLine[]>([]);
readonly lines = this._lines.asReadonly();
```

A component can display the conversation but cannot quietly reassign it. Every
change goes through a method on the store, which is the only place that has to
be got right.

### The four stores

| Store           | Holds                                   | Notable behaviour                            |
| --------------- | --------------------------------------- | -------------------------------------------- |
| `SessionStore`  | Who is signed in, the token             | Obtains the XSRF token at startup            |
| `ChatStore`     | The conversation, waiting state, errors | Optimistic messages; returns text on failure |
| `CampaignStore` | Campaigns and characters                | Sorts by title **in the browser**            |
| `SettingsStore` | Preferences                             | An `effect` applies the theme automatically  |

They are `providedIn: 'root'`, so there is exactly one of each and state
survives navigation. Going to Settings and back does not lose the conversation.

### Two behaviours worth understanding

**Optimistic messages.** When the player sends something, it appears
immediately with `pending: true`, before the backend has confirmed anything.
Waiting for the round trip would mean staring at an empty box for the several
seconds a Dungeon Master takes to think.

If the send fails, the optimistic message is removed and `send()` **returns the
text** so the component can restore it to the input box. Losing what somebody
wrote to a network blip is the kind of small cruelty that makes people stop
using software, so it is pinned down by a test.

**Sorting campaigns by title happens here, not in the database.** Campaign
titles are encrypted, so the database genuinely cannot read them, let alone
order them. This is the clearest everyday example of what the privacy design
costs — and why campaign lists are paged rather than unbounded.

---

## Routing

Defined in `app.routes.ts`. Every screen uses `loadComponent`, so its code is
downloaded the first time someone visits it rather than all of it arriving up
front. The build output shows this: a small initial bundle plus one lazy chunk
per screen.

`withComponentInputBinding()` lets a route parameter arrive as a component
input, so components do not subscribe to the router just to read an id:

```typescript
readonly campaignId = input.required<string>();
```

**No personal data appears in any URL.** Only opaque identifiers. URLs reach
browser history, server access logs, and the `Referer` header sent to any site
the user clicks through to — all outside the encryption boundary.

---

## The API layer

Three pieces, each with one job:

- **`api.types.ts`** — the shapes exchanged with the backend. Hand-written
  rather than generated, because these are where each field's privacy
  classification is recorded, and a generated file is one nobody reads.
- **`api.client.ts`** — a thin wrapper knowing where the backend is. Centralised
  so there is exactly one place the address is read, which makes it easy to
  prove no `localhost` is written into any source file.
- **The interceptors** — cross-cutting behaviour applied to every request.

**These types are not checked against the backend by the compiler.** The
boundary between two programs is not type-checked, so a mismatch shows up as
`undefined` at runtime. When a Pydantic model changes, change these in the same
commit.

### The interceptors, and why their order matters

```
credentials  →  xsrf  →  auth  →  error  →  the network
```

| Interceptor   | Does                                    | Why it is where it is                                                                |
| ------------- | --------------------------------------- | ------------------------------------------------------------------------------------ |
| `credentials` | Sets `withCredentials` for our API      | Must run first, so the browser is told to include cookies before anything reads them |
| `xsrf`        | Reads the token cookie, sets the header | Needs the cookie that `credentials` enabled                                          |
| `auth`        | Adds the `Authorization` header         | Independent; grouped with the other outgoing work                                    |
| `error`       | Normalises every failure                | Outermost on the way back, so it sees failures from all of the above                 |

Each is scoped to the configured API address. Attaching a session token or
`withCredentials` to _every_ request would hand credentials to any third party
the application ever calls.

---

## Where XSRF tokens are handled

`core/http/xsrf.interceptor.ts`.

**Angular already has XSRF support, and this application enables it** — but it
is not sufficient on its own, for a reason easy to miss and painful to
diagnose: **Angular only attaches the token to relative URLs.** It assumes the
API shares the page's origin. Ours does not, so every request is absolute, and
Angular attaches nothing. Every state-changing request would be refused with a
403 giving no hint why.

The custom interceptor closes that gap, attaching the token to requests aimed
at the configured API address and nowhere else.

**The deployment constraint this implies** is the single thing most likely to
break a first deployment. A browser will not let a page read a cookie set by a
different domain. Locally both are `localhost`, and cookies ignore port
numbers, so it works with no effort. In production it works only if:

```
frontend   https://app.example.com     (Hostinger)
backend    https://api.example.com     (Fly.io)
COOKIE_DOMAIN=.example.com             (set on the backend)
```

If the backend stays on a `*.fly.dev` address, the browser treats the two as
unrelated sites and nothing can be saved. Plan for it rather than debugging it
on launch day.

---

## Runtime configuration

The backend address is **not** compiled in. It lives in `public/config.json`,
fetched by `main.ts` before Angular starts.

The reason is the deployment model. The Angular app is uploaded to Hostinger as
plain files. With the address compiled in, changing it — moving the backend,
adding staging, fixing a typo in a domain — would mean rebuilding and
re-uploading everything. This way it is one file edited on the server. **Build
once, configure anywhere.**

If the file is missing or malformed, the application **refuses to start** and
writes a plain HTML message naming the file. The alternative is a blank white
page and a confusing network error later.

---

## Why SSR is off

Angular can run in two modes: build to plain files any web server can hand out,
or run a Node.js program assembling each page server-side.

**This project uses plain files, and Server-Side Rendering must stay off.**

Hostinger's static hosting serves files. It does not run a Node process. SSR
would make the frontend undeployable to the chosen tier. This is a hard
constraint flowing from the hosting decision, not a preference.

**What is given up:** search engines see an empty page until JavaScript runs
(irrelevant behind a login), and the first load is slightly slower because the
code must arrive before anything draws.

**What would need to change to enable it later:**

1. **The hosting tier must move off Hostinger** to something that runs Node.
   This is the real cost; everything below is small by comparison.
2. **Every use of `window`, `document`, `localStorage` and `navigator` needs a
   guard**, because none exists on a server. In this codebase that means
   `readCookie`, `SettingsStore`'s theme effect, `VoiceRecorder`, and the
   startup failure handler in `main.ts`.
3. **`loadAppConfig` needs a server-side path**, since `fetch('config.json')`
   with a relative URL has no meaning on a server.
4. **Cookie-based XSRF needs rethinking**, because the server-rendered first
   request happens before the browser holds a token.
5. **The voice recorder must be excluded from server rendering entirely.**

None of this is difficult; all of it is invisible until SSR is switched on, at
which point it appears as a pile of `ReferenceError: window is not defined`.

---

## Accessibility, built in rather than added

- **Landmarks.** Real `<header>`, `<nav>`, `<main>`, `<footer>` elements, so a
  screen reader can jump between regions.
- **A skip link**, first in the page. Without it, keyboard users tab through
  every navigation link on every page before reaching the content.
- **Visible focus outlines**, never removed. Removing them makes an interface
  unusable for anyone navigating by keyboard.
- **`aria-live` on the conversation**, so new narration is announced without
  interrupting. Without it a blind player would not know the DM had replied.
- **Reduced motion honoured** from both the operating system setting and the
  in-app one. For some people motion causes genuine nausea.
- **Colour never carries meaning alone.** Every banner pairs its colour with an
  icon and words, because roughly one man in twelve cannot reliably tell red
  from green.

---

## Related documents

- [CONVENTIONS.md](CONVENTIONS.md) — house style.
- [UI_PATTERNS.md](UI_PATTERNS.md) — the design system, and telling mocks from
  real code.
- [VOICE_INPUT.md](VOICE_INPUT.md) — audio and the permission flow.
- [TESTING.md](TESTING.md) — what is tested and how.
