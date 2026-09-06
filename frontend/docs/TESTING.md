# Frontend Testing

**Read this when** you are writing a frontend test.

```bash
npm test                      # all of them, vitest
npm test -- --coverage
```

Angular 22 uses **vitest** with **jsdom**, a simulated browser environment.
Tests are `*.spec.ts` beside the code they test.

---

## What gets mocked, and what does not

| Thing                            | Mocked?    | Why                                                                                                      |
| -------------------------------- | ---------- | -------------------------------------------------------------------------------------------------------- |
| `HttpClient` / `ApiClient`       | **Yes**    | A test must never make a real request: slow, flaky, spends AI quota, sends test content to a third party |
| `fetch` for `config.json`        | **Yes**    | Stubbed per test so failure paths can be exercised                                                       |
| Signal stores                    | **No**     | They are the logic under test                                                                            |
| Pure functions                   | **No**     | Nothing to mock                                                                                          |
| `document.cookie`                | **No**     | jsdom provides a real one                                                                                |
| `MediaRecorder` / `getUserMedia` | Not tested | jsdom has no audio. Verified by hand — see below                                                         |

The general rule: **mock the boundary, test everything inside it.**

---

## What the 52 tests prove

### `xsrf.interceptor.spec.ts`

Small, but this is the function whose silent failure produces the most
confusing symptom in the whole application: every save returning 403 with no
clue why.

- A cookie is found by name, and absence returns `null`.
- **A similarly named cookie is not mistaken for it** — the classic
  `document.cookie` parsing bug.
- The right one is found among several.
- Encoded values are decoded, since tokens contain `+`, `/` and `=`.

### `app-config.spec.ts`

The failure paths matter more than the success path here.

- The backend address is read, and a trailing slash is stripped (without which
  every URL contains a doubled slash, which some servers treat as a different
  path and answer with a puzzling 404).
- **Startup fails loudly** when the file is missing, when `apiBaseUrl` is
  absent, or when it cannot be fetched at all.

That last group is the point. An application that started without a backend
address would fail later with a network error nobody could trace back to a
configuration problem.

### `chat.store.spec.ts`

- A successful turn produces both the player message and the reply, in order.
- **A failed send returns the text so it can be restored**, and removes the
  optimistic message. Losing what somebody typed to a network blip is the kind
  of small cruelty that makes people abandon software, so it is pinned down
  rather than left to good intentions.
- The correlation identifier is kept for the user to quote.
- Empty messages never reach the network.
- **Scrubbing is surfaced**, so the player can see something was removed before
  their words were sent to Google.
- Changing campaign clears the conversation.

### `dice.spec.ts`

The rules of rolling, which are arithmetic and so can be pinned down exactly.

- **Every face of a d20 is reachable.** 4,000 rolls must produce all 20 values.
  A die that never rolls a 20 is broken, and this is the cheapest way to catch
  an off-by-one in the modulo.
- **Advantage really takes the higher of two**, checked over 200 rolls rather
  than once, and the discarded die is kept.
- **The modifier is applied once, not once per die.** `3d6+5` is easy to write
  as `+5` three times.
- Advantage is ignored on dice where the rules do not define it.
- A critical is flagged only on a single d20 — eight d6 for a fireball totalling
  20 is not a critical hit.

### `polyhedra.spec.ts`

The shapes of the dice. These are the kind of thing that looks almost right
when it is wrong, so the properties that make a solid a solid are checked
directly rather than left to the eye.

- **Every die has the number of faces its name promises.** A d20 with nineteen
  faces is the reason the file exists.
- **Every face has the right number of corners** — triangles for the d4, d8 and
  d20, squares for the d6, kites for the d10, pentagons for the d12.
- **Every face of a die is the same size and the same distance from the
  centre.** If the derivation picks up a stray corner, one face comes out
  bigger. This is the test that caught the original wrong-shapes bug, and it is
  the reason that bug did not ship.
- **Roll a 17, see the 17** — checked for every face of every die.
- Opposite faces add up to one more than the number of sides, the way
  manufactured dice are numbered.

That last group is worth dwelling on. Nothing here renders anything, and yet it
is a genuine test of what appears on screen — because the geometry was made a
pure function first, and only then turned into styles. Anything that could only
be checked by looking at it would not have been checked at all.

---

## Writing a test

Name it as a sentence describing behaviour:

```typescript
it('hands the text back when the send fails, rather than losing it', ...)
```

For a store, provide a fake `ApiClient` through `TestBed`:

```typescript
class FakeApiClient {
    post = vi.fn();
    get = vi.fn();
}

TestBed.configureTestingModule({
    providers: [ChatStore, { provide: ApiClient, useValue: api }]
});
```

Return `of(value)` for success and `throwError(() => ({ failure: {...} }))` for
failure — the shape the error interceptor produces.

**Read signals as functions in assertions:** `store.lines()`, not
`store.lines`.

---

## Rules for test data

**No real personal data, ever.** Every address uses `example.com`, which IANA
reserves for documentation. Every name is invented. Test data leaks — into bug
reports, screenshots, and pasted output.

**No real API keys, no real tokens.**

---

## What is not covered, and how it is verified instead

Being explicit about the gaps rather than implying the suite covers everything.

**Voice recording.** jsdom has no `MediaRecorder` and no microphone. Mocking
the whole audio pipeline would test the mock rather than the behaviour. Instead
it is verified by hand against the checklist in
[VOICE_INPUT.md](VOICE_INPUT.md): permission granted, permission denied,
permission denied and then re-asked, no microphone present, cancel mid-recording,
and the 120-second self-stop. The one that matters most is **confirming the
browser's recording indicator disappears** when recording ends — if it does not,
the microphone is still live.

**Full screen rendering.** Component tests would mostly assert that a template
contains the text of that template. The screens are verified by using them.

**Accessibility.** Checked by hand: tab through every screen, confirm focus is
always visible, confirm the skip link works, and run through once with the
operating system's screen reader.

**The API contract.** The boundary between two programs is not type-checked. A
mismatch between `api.types.ts` and the backend's Pydantic models shows up as
`undefined` at runtime. **When a Pydantic model changes, change the TypeScript
type in the same commit.**

---

## Coverage

No enforced percentage — a percentage measures lines executed rather than
behaviour verified. What is expected:

- Every store has tests for its success **and** failure paths.
- Every pure function that parses or transforms input has tests, including the
  malformed cases.
- Anything that would silently lose a user's work has a test.

---

## Related documents

- [CONVENTIONS.md](CONVENTIONS.md) — house style.
- [ARCHITECTURE.md](ARCHITECTURE.md) — what the stores do.
- [Backend testing](../../backend/docs/TESTING.md) — the other 88.
