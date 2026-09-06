# Frontend Conventions

**Read this when** you are about to write a component and want to match what is
already there.

---

## Components are standalone

No NgModules anywhere. Every component declares its own imports:

```typescript
@Component({
  selector: 'app-campaign-list-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, Banner],
  template: `...`,
})
export class CampaignListPage {}
```

**Always `ChangeDetectionStrategy.OnPush`.** With signals it is strictly
better: Angular re-renders only when a signal a component actually reads has
changed, rather than checking everything after every event.

---

## Naming

| Thing | Style | Example |
|---|---|---|
| Files | kebab-case | `campaign-list-page.ts` |
| Classes | PascalCase | `CampaignListPage` |
| Selectors | `app-` prefix, kebab | `app-campaign-list-page` |
| Screens | `*Page` suffix | `ChatPage` |
| Stores | `*Store` suffix | `SessionStore` |
| Private signals | leading underscore | `_lines` |

Angular 22's generator omits `.component` from filenames. That convention is
followed here: `chat-page.ts`, not `chat-page.component.ts`.

---

## When to use a signal, and when an input

This is the question that comes up most often.

**Use `input()` when the value comes from outside the component** — a parent, or
a route parameter. It is read-only from the component's point of view.

```typescript
readonly campaignId = input.required<string>();   // from the URL
readonly kind = input<BannerKind>('info');        // from a parent
```

**Use `signal()` for state the component itself owns** — usually something the
user is in the middle of doing.

```typescript
readonly draft = signal('');            // what is being typed
readonly menuOpen = signal(false);      // is the menu showing
```

**Use `computed()` for anything derived.** Never store what can be calculated —
two pieces of state that must agree will eventually disagree.

```typescript
readonly canSend = computed(() => this.draft().trim().length > 0 && !this.waiting());
```

**Use a store when two screens need the same state**, or when it must survive
navigation. The conversation lives in `ChatStore` precisely so that visiting
Settings and coming back does not lose it.

**Use `effect()` sparingly**, only for synchronising with something outside
Angular. There are two in this codebase: applying the theme to
`document.documentElement`, and scrolling the newest message into view. Both
reach out to the browser, which is what an effect is for. If you find yourself
writing an effect that sets another signal, you wanted `computed()`.

---

## Templates

**Modern control flow only** — `@if`, `@for`, `@switch`. Not `*ngIf`, not
`*ngFor`.

**Always give `@for` a `track`.** Without it Angular rebuilds every row on every
change, losing focus and scroll position.

```html
@for (line of lines(); track line.id) { ... }
```

**Use `@if (thing(); as value)`** to avoid calling a signal repeatedly:

```html
@if (error(); as message) {
  <app-banner kind="danger">{{ message }}</app-banner>
}
```

**Keep logic out of templates.** A template should read like a description of
the screen. If an expression needs a comment, it belongs in a `computed()`.

**Write real HTML.** `<button>` for actions, `<a>` for navigation, `<label>`
attached to every input. A `<div>` with a click handler is invisible to
keyboards and screen readers.

---

## Styles

**Component styles for anything specific to that component.** Angular scopes
them automatically, so a class name cannot leak.

**Shared classes in `styles.scss`** for genuinely global patterns: `.btn`,
`.card`, `.field`, `.banner`, `.page`.

**Always use the design tokens.** `var(--surface)`, never `#1a1d26`. The theme
switch works by redefining those variables; a hard-coded colour will not
change with it and will be unreadable in the other theme.

Small components use inline `styles: []`; larger ones use a `.scss` file. The
line is roughly forty lines of CSS.

---

## TSDoc comments

**Every function, component and exported value gets one**, written for a reader
who has never programmed.

The standard is higher than restating the signature:

```typescript
/**
 * Send whatever is in the input box.
 *
 * @param inputMode Whether this came from typing or from speech.
 * @returns Nothing. If the send fails the text is put back in the box, because
 *   losing what somebody wrote to a network blip is unforgivable.
 */
async send(inputMode: 'typed' | 'voice' = 'typed'): Promise<void> {
```

On a component class, explain what the screen is for and — importantly — what
about it is real and what is stubbed.

---

## Handling errors

Never let a raw HTTP error reach a template. The error interceptor turns every
failure into an `ApiError` carrying a code, a message safe to display, and the
correlation identifier.

**Always surface the correlation identifier on a failure.** It is the only
thing needed to investigate, and the backend cannot look up a user's data to
help them.

```html
@if (correlationId(); as id) {
  <p class="small">If you report this, quote: <code class="mono">{{ id }}</code></p>
}
```

**Branch on `code`, never on message text.** Messages get reworded; codes are a
contract.

---

## Marking stubbed screens

Any screen whose behaviour is not real uses `<app-stub-notice>`, stating what
is not implemented **and** what genuinely is:

```html
<app-stub-notice
  detail="Signing in does not yet create a real, protected session."
  whatIsReal="Your password is genuinely checked against an Argon2id hash."
/>
```

Both halves matter. "This is a preview" alone is misleading in the other
direction — on most of these screens a good deal is real, and it is worth
saying which parts.

---

## Things never to do

- **Never put an API key in this application.** There is no setting that accepts
  one. A key in a web page is a key given to everybody.
- **Never write `localhost` in a source file.** It belongs in
  `public/config.json`.
- **Never put personal data in a URL** or in `localStorage`.
- **Never call `HttpClient` directly** — use `ApiClient`, so the base address
  and the interceptors apply.
- **Never remove a focus outline.**
- **Never use `any`.** If a type is genuinely unknown, use `unknown` and narrow
  it.

---

## Commits

Plain and descriptive. Subject line alone by default; a body only when the
change is not self-explanatory, and then one paragraph.

**No AI attribution** — no `Co-Authored-By`, no "generated with", no footers.
