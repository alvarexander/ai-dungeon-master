# AGENTS.md — Frontend

The Angular application for the AI Dungeon Master. It draws every screen,
records voice input, and talks to the Python backend. It builds to plain static
files with no server process, because it is deployed to static hosting.

**Read [SYSTEM_GUIDE.md](../SYSTEM_GUIDE.md) first for anything that spans both
repositories** — the API contract, the shared privacy boundary, and what
crosses the network. It is authoritative where this file and it disagree.

---

## Hard constraints — never violate these

1. **Server-Side Rendering stays off.** Never scaffold or enable Angular
   Universal. The hosting tier serves files and runs no Node process, so SSR
   would make this undeployable. See
   [ARCHITECTURE.md](docs/ARCHITECTURE.md#why-ssr-is-off).
2. **The Gemini API key never reaches this application.** There is no setting
   that accepts one. Every AI call happens on the backend. A key in a web page
   is a key given to everybody.
3. **No `localhost` in any source file.** The backend address comes from
   `public/config.json`, read at runtime. That is what lets a deployed build be
   pointed elsewhere by editing one file.
4. **No personal data in URLs or in `localStorage`.** Opaque identifiers only.
5. **Standalone components and signals.** No NgModules. No `BehaviorSubject`
   where a signal will do.
6. **Every new function and component gets a TSDoc comment** written for a
   reader who has never programmed. Explain why, not only what.
7. **Icons are inline SVG from `<app-icon>`, never an emoji and never a web
   font.** A font from `fonts.googleapis.com` contacts Google on every page
   load, blocks rendering, and breaks offline.
8. **Stubbed screens must say so on screen**, using `<app-stub-notice>`. A mock
   indistinguishable from working software is a trap.
9. **Honour `prefers-reduced-motion`.** Every animation either stops or
   shortens. For some people motion causes genuine nausea.
10. **No AI attribution in commits.** No `Co-Authored-By`, no "generated with"
   lines, no tool footers.

---

## Local setup

The backend must be running first — see [RUNNING.md](../RUNNING.md).

```bash
npm install
npm start                 # http://localhost:4200
```

```bash
npm test                  # 58 tests, vitest
npm run build             # production build into dist/ai-dungeon-master/browser

npm run lint              # ESLint
npm run prettier:check    # is everything formatted?
npm run format            # prettier --write, then eslint --fix
```

**Formatting is not a matter of taste here.** Prettier owns it — 4-space
indent, single quotes, no trailing commas, 120 columns — matching the other
repositories. ESLint owns correctness only; do not add stylistic rules, they
just fight Prettier.

---

## Layout

```
public/config.json        runtime configuration; NOT baked into the build
src/app/
  core/
    app-config.ts         fetches config.json before the app starts
    api/                  typed API client and the shapes it exchanges
    dice/                 rolling rules, kept pure and testable
    http/                 interceptors: credentials, xsrf, auth, error
    state/                signal stores: session, chat, campaign, settings
    voice/                recording, waveform analysis, speech synthesis
  shared/ui/              banner, stub notice, icon, waveform
  features/
    chat/                 the play screen
    dice/                 the dice tray and the 3D die
    ...                   one folder per screen
  app.ts / app.html       the shell: navigation and layout
```

---

## Documentation index

| File | Read it when |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | You need the component hierarchy, routing, state, or why SSR is off |
| [CONVENTIONS.md](docs/CONVENTIONS.md) | You are writing a component and want the house style |
| [UI_PATTERNS.md](docs/UI_PATTERNS.md) | You need the design system, or to tell a mock from real code |
| [VOICE_INPUT.md](docs/VOICE_INPUT.md) | You are touching audio, the waveform, the Dungeon Master's voice, or hands-free mode |
| [DICE.md](docs/DICE.md) | You are touching the dice, the 3D die, or advantage |
| [TESTING.md](docs/TESTING.md) | You are writing tests |
| [GLOSSARY.md](docs/GLOSSARY.md) | A word here means nothing to you |

---

## Phase 1 status

**Fully working:** the chat loop, voice input with a live waveform, the Dungeon
Master reading its narration aloud, hands-free conversation, the dice tray with
a 3D die and advantage, campaigns, characters, settings, account deletion, and
every screen's layout.

**Deliberately stubbed, and labelled on screen:** sign-in, registration and
password reset produce a placeholder session rather than a real one. The
backend refuses to run this way in production.

---

## Definition of done

- `npm test` passes.
- `npm run lint` passes and `npm run prettier:check` is clean.
- `npm run build` succeeds with no warnings.
- Every new function and component has a beginner-facing TSDoc comment.
- New screens are keyboard navigable and have visible focus outlines.
- Any stubbed behaviour is marked with `<app-stub-notice>`.
- No `localhost`, no API key, and no personal data in a URL.
