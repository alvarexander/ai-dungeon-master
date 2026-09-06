# Glossary — frontend

**Read this when** a word in the frontend documentation means nothing to you.

Terms shared with the backend — API, CORS, XSRF, encryption, tokens, and so on
— are in the [shared glossary](../../docs/GLOSSARY.md). This file covers what
is specific to the Angular application.

---

## The web page itself

**DOM (Document Object Model)** — the browser's live representation of the page
as a tree of elements. When Angular "renders", it changes the DOM.

**Element** — one node in that tree: a `<button>`, a `<div>`.

**Event** — something that happened: a click, a key press, a form change.

**Cookie** — a small piece of text the browser stores for a site and attaches
automatically to requests. Our XSRF token lives in one.

**`localStorage`** — a place the browser stores text for a site, which survives
closing the tab. Unlike a cookie it is not sent automatically. Readable by any
script on the page, which is why a real session token should not live there.

**Same-origin policy** — the browser rule that a page from one origin cannot
read another origin's cookies, storage, or responses. It is the foundation the
XSRF defence rests on.

**Bundle** — the compiled JavaScript the browser downloads. **Chunk** — one
piece of it. Lazy loading splits the application into chunks so only the screen
being visited is downloaded.

**Static build** — the output of `npm run build`: plain files any web server can
serve, with no program running on the server.

---

## Angular

**Component** — one piece of interface: a class holding the logic and a
template describing the markup. Everything visible is one.

**Standalone component** — a component declaring its own imports, with no
NgModule. All of ours are standalone; NgModules are not used at all.

**Template** — the HTML for a component, with Angular's syntax added.

**Selector** — the tag name a component is used as, e.g. `<app-banner>`.

**Directive** — something that changes an element's behaviour without being a
component of its own, e.g. `routerLink`.

**Pipe** — a small transformation used in a template, written with `|`, e.g.
`{{ tone | titlecase }}`.

**Signal** — a value that knows who is reading it. When it changes, everything
reading it updates automatically. The core of how state works here.

**`computed()`** — a signal derived from other signals, recalculated when they
change. Use it instead of storing anything that can be worked out.

**`effect()`** — code that re-runs when the signals it reads change. Used only
for reaching outside Angular — applying the theme, scrolling a message into
view. If an effect sets another signal, you wanted `computed()`.

**`input()`** — a value passed in from outside: a parent component, or a route
parameter. Read-only from inside.

**Zoneless** — Angular's newer mode where it does not patch every browser API to
detect changes, relying on signals instead. This application is zoneless, which
is why signals are used rather than plain properties.

**Change detection** — Angular working out what needs re-rendering.
**OnPush** — the strategy used throughout: re-render only when a signal the
component actually reads has changed.

**Dependency injection / `inject()`** — asking Angular for a service rather than
constructing one.

**Service** — a class holding logic or state, shared between components.
**`providedIn: 'root'`** means there is exactly one for the whole application.

**Router** — the part of Angular deciding which screen matches the current
address. **Route** — one entry in that table. **`<router-outlet>`** — where the
matched screen is drawn.

**Lazy loading (`loadComponent`)** — downloading a screen's code the first time
it is visited rather than up front.

**Interceptor** — a function every HTTP request passes through, for
cross-cutting work like adding a header.

**Observable** — a stream of values over time, from the RxJS library. Angular's
`HttpClient` returns one. `firstValueFrom` turns it into a promise, which is
what this codebase mostly does.

**`TestBed`** — Angular's test harness for constructing components and services
with dependencies replaced.

---

## Tooling

**Node.js** — the program that runs JavaScript outside a browser. Used only to
*build* this application, never to run it.

**npm** — the package manager. `npm install` fetches libraries;
`npm start` runs the development server.

**Angular CLI (`ng`)** — the command-line tool that builds and serves the app.

**TypeScript** — JavaScript with types added, checked at build time and removed
from the output.

**SCSS** — a superset of CSS allowing nesting and variables. Compiled to CSS at
build time.

**CSS custom property** — a variable defined in CSS itself, e.g.
`var(--surface)`. Unlike an SCSS variable it exists at runtime, which is what
makes theme switching possible.

**vitest** — the test runner. **jsdom** — a simulated browser it runs tests in.

**Prettier** — the code formatter.

---

## This application's own vocabulary

**Store** — a service holding state as signals: `SessionStore`, `ChatStore`,
`CampaignStore`, `SettingsStore`.

**Runtime configuration** — `public/config.json`, fetched when the page loads
rather than compiled in, so a deployed build can be pointed at a different
backend by editing one file.

**Optimistic message** — the player's message shown immediately, before the
backend confirms it. Removed and handed back if the send fails.

**Stub notice** — the banner marking a screen whose behaviour is not yet real.

**Demo mode** — the state where authentication is stubbed, shown as a strip
across the top of every page.

**Correlation identifier** — the value shown on error screens, which is all
that is needed to investigate a problem without reading anyone's data.

**Design token** — a named value in the design system, e.g. `--space-4`. Always
used instead of a literal.

**Measure** — the maximum comfortable line length for reading, set to 68
characters.

---

## Accessibility

**Screen reader** — software that reads a page aloud. **Landmark** — a
structural element (`<nav>`, `<main>`) it can jump between.

**`aria-live`** — marks a region whose changes should be announced. `polite`
waits for a pause; `assertive` interrupts. The conversation is `polite`.

**Skip link** — a link, first in the page, jumping straight to the content, so
keyboard users need not tab through the navigation on every screen.

**Focus** — which element currently receives keyboard input.
**`:focus-visible`** — the browser's judgement that focus should be shown,
which is true for keyboard use and not for mouse clicks.

**`prefers-reduced-motion`** — an operating system setting saying the user does
not want animation. Honoured completely, because for some people motion causes
genuine nausea.

**WCAG AA** — the accessibility standard aimed at here. Its contrast
requirement is 4.5:1 for body text.
