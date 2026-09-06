# UI Patterns

**Read this when** you are building a screen and want it to look like the rest
of the application, or when you need to tell a working screen from a mock.

---

## Telling a mock from real code

**This is the most important section here.** Several screens look finished and
are not. The sign-in form validates properly and looks exactly like a working
one — but the session it creates is a placeholder the backend does not verify.

A mock indistinguishable from working software is a trap: for a user who
assumes their account is protected, and for whoever picks this up later and
assumes it is done.

### The three signals

**1. `<app-stub-notice>` on the screen itself.** A yellow banner stating what
is not implemented and what genuinely is.

**2. The demo-mode strip across the top of every page**, shown whenever
`session.isStub()` is true.

**3. `is_stub: true` in the API response.** The backend says so too.

### Which screens are which

| Screen | Status | What is real |
|---|---|---|
| Play (chat) | **Fully working** | Everything, including the AI |
| Campaigns | **Fully working** | Real create, list, delete, real encryption |
| Characters | **Fully working** | Real sheets, hit point arithmetic, encryption |
| Settings | **Fully working** | Real preferences, saved to the backend |
| Account — details, activity | **Fully working** | Reads the real profile |
| Account — deletion | **Fully working** | Genuinely destroys the encryption key |
| Your data (privacy) | **Fully working** | Static content, but true |
| Sign in | **Stubbed session** | Argon2id password check, encrypted email lookup, rate limiting are all real. The *token* is not |
| Sign up | **Stubbed session** | Registration genuinely creates an encrypted account |
| Forgot password | **Fully stubbed** | Nothing is sent; needs email delivery |
| Account — change password/email | **Fully stubbed** | Same reason |

**If you make a stubbed screen real, remove its `<app-stub-notice>` in the same
commit.** A stale warning trains people to ignore warnings.

---

## Design tokens

Defined once in `styles.scss` as CSS custom properties. **Always use these,
never a literal colour** — the theme switch works by redefining them, so a
hard-coded colour will not change with it and will be unreadable in the other
theme.

### Colour

| Token | For |
|---|---|
| `--bg` | The page behind everything |
| `--surface` | Cards and panels |
| `--surface-raised` | Something sitting on a card |
| `--surface-sunken` | Inputs, wells |
| `--ink` | Body text |
| `--ink-muted` | Supporting text |
| `--ink-faint` | Labels, placeholders |
| `--accent` | Old gold — the one brand colour |
| `--danger` / `--success` / `--warning` / `--info` | Meaning |
| `--border` / `--border-strong` | Dividers and outlines |
| `--focus` | The focus ring. Never override this |

Every foreground and background pair meets the WCAG AA contrast ratio of 4.5:1
for body text, in both themes.

### Spacing

`--space-1` (4px) through `--space-8` (64px), roughly doubling. Using a scale
rather than arbitrary numbers is what makes unrelated screens look like one
application.

### Type

- `--font-body` — the system sans, for interface text. It should feel native.
- `--font-narrative` — a serif, used **only** for the Dungeon Master's
  narration, campaign titles and character names. Prose reads better in a
  serif, and it makes the story feel different from the controls around it.
- `--font-mono` — for identifiers, especially correlation IDs.

`--measure: 68ch` caps line length for reading. Lines much longer than this are
tiring, because the eye loses its place returning to the start.

---

## Shared components

### `<app-banner>`

Every message in the application. Four kinds: `info`, `warning`, `danger`,
`success`.

```html
<app-banner kind="danger" title="That did not work">
  <p>{{ message }}</p>
</app-banner>
```

Handles two accessibility details automatically, which is the main reason it is
one component rather than repeated styling:

- `role="alert"` and `aria-live="assertive"` for `danger`, so a screen reader
  interrupts. `role="status"` and `aria-live="polite"` otherwise, so it waits.
- **An icon alongside the colour.** Roughly one man in twelve cannot reliably
  distinguish red from green, so colour never carries meaning alone.

### `<app-stub-notice>`

See above. Takes `detail` (what is not real) and `whatIsReal`.

---

## Shared classes

| Class | Use |
|---|---|
| `.page` | Screen wrapper. Add `.page--narrow` for forms and reading |
| `.card` | A panel |
| `.field` with `.field__label`, `.field__hint`, `.field__error` | A form field |
| `.input`, `.select`, `.textarea` | Form controls |
| `.btn` with `--primary`, `--ghost`, `--danger`, `--sm`, `--block` | Buttons |
| `.row`, `.stack`, `.grid`, `.spacer` | Layout |
| `.muted`, `.small`, `.mono` | Text |
| `.visually-hidden` | Visible only to screen readers |

---

## Form patterns

**Every input has a `<label>`.** Placeholder text is not a label — it disappears
when typing starts, and screen readers treat it inconsistently. Where a visible
label would be redundant, use `.visually-hidden`.

**Hints explain, and often explain privacy:**

```html
<span class="field__hint">
  Encrypted before it is stored. Even someone holding a complete copy of the
  database cannot read it.
</span>
```

This is deliberate. People make better decisions about what to type when they
know where it goes, and the field hint is the moment they are thinking about it.

**Errors replace hints, never stack on top:**

```html
@if (passwordTooShort()) {
  <span class="field__error">At least 12 characters. Length matters far more
    than punctuation.</span>
} @else {
  <span class="field__hint">Hashed with Argon2id.</span>
}
```

**Say what to do, not what went wrong.** "At least 12 characters" beats
"Invalid password".

**Disable the submit button until the form is valid**, using a `computed()`.
Better than letting someone submit and then telling them off.

---

## Destructive actions

Two levels, matched to how bad the mistake would be.

**Two-click confirmation** for reversible-ish things. Deleting a campaign turns
the button into "Really delete?" for five seconds. No modal — modals for every
delete are heavy-handed — but a single misplaced click is not enough.

**Typed confirmation plus a tickbox** for account deletion. Deliberate friction
on an action nobody, including us, can reverse:

```html
<label class="field">
  <span class="field__label">Type your username to confirm</span>
  ...
</label>
```

The warning explains crypto-shredding in plain language rather than saying
"this cannot be undone" and hoping.

---

## Loading and waiting

**Never a bare spinner where the wait is meaningful.** The chat screen shows
three pulsing dots under "DUNGEON MASTER" — the same shape a reply will occupy,
so the layout does not jump when it arrives.

**Optimistic display** for the player's own message: it appears immediately at
55% opacity, then becomes solid when confirmed.

**Never block the whole screen.** Disable the specific control that is busy.

---

## Empty states

Every list that can be empty explains what the thing is and offers the next
step. The campaign list does not say "No campaigns" — it explains what a
campaign is and offers two ways forward, including "just start playing".

The chat screen's empty state gives three example opening lines. A blank box
labelled "What do you do?" is intimidating if you have never played.

---

## Responsive layout

One breakpoint, at 820px, where the navigation collapses behind a button. The
breakpoint is **where the layout actually breaks**, not a device size — device
widths change; the point at which links stop fitting does not.

The chat composer wraps below 600px so the message box gets full width.

---

## Voice

- **Idle:** a microphone button beside the send button.
- **Recording:** the composer is replaced by a red bar with a pulsing dot, a
  running timer, Cancel and Done. Unmistakable — the user must never be unsure
  whether the microphone is live.
- **Transcribing:** the button shows an ellipsis and inputs are disabled.
- **Unavailable:** the button is absent and a banner explains why. Typing is
  never affected.

---

## Writing style in the interface

- **Say what happened and what to do.** "Too many requests. Please wait 42
  seconds" beats "Rate limit exceeded".
- **No jargon.** Not "XSRF token invalid" but "Reload the page and try again".
- **Be honest about limits.** The privacy page says outright that the scrubber
  cannot catch a name in an ordinary sentence.
- **Never blame the user.** "That password starts with one of the most commonly
  guessed words", not "Weak password".
- **Sentence case** for headings and buttons. Not Title Case.

---

## Related documents

- [ARCHITECTURE.md](ARCHITECTURE.md) — how screens fit together.
- [CONVENTIONS.md](CONVENTIONS.md) — code style.
- [VOICE_INPUT.md](VOICE_INPUT.md) — the voice states in detail.
