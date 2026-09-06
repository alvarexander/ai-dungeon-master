# Voice Input

**Read this when** you are touching audio recording, the microphone permission
flow, or the speech-to-text path.

---

## The short version

The browser records audio. The recording is uploaded to **our own backend**,
which transcribes it locally. The audio is discarded. It is never sent to
Google or anyone else.

---

## Why not the browser's built-in speech recognition

Browsers have a `SpeechRecognition` API. It would replace this entire document
with about five lines of code.

**In Chrome, it works by streaming the raw microphone audio to Google's
servers.**

That would place a recording of the user's voice — in their home, with whoever
else is audible in the room — outside the boundary this whole application
exists to maintain. Every other control in the project would be undermined by
it: there is little point encrypting a transcript at rest if the audio it came
from was posted to a third party on the way in.

**A tempting newer option was also rejected.** Google now offers a dedicated
speech model through the same API we already use for the Dungeon Master. Same
objection: it is a third party receiving raw audio.

### The honest tension

We _do_ send the transcribed text to Gemini, because that is the product. So
why fight over the audio?

Because the two are not equivalent:

- **Text can be scrubbed** of emails, phone numbers and postcodes before it is
  sent. It can be inspected, logged as a length, and reasoned about.
- **Audio cannot be scrubbed.** It carries the speaker's identity in its
  waveform whatever the words are — an adult or a child, an accent, a health
  condition audible in a voice — plus whatever else was happening in the room.

Text is a controllable leak. Audio is not.

### What it costs

Real money, and this is the clearest example in the project of a privacy
control with a price tag. Transcription is computation, and it now happens on
our server instead of Google's. The Whisper `base` model needs roughly 1 GB of
memory and a second or two of processor time per utterance, which moves the
Fly.io machine from the smallest size to a 1 GB instance — about **five dollars
a month**. See [COSTS](../../docs/COSTS.md).

---

## How it works

```
microphone → MediaRecorder → WebM/Opus blob → upload → our server
                                                          ↓
                                              faster-whisper, locally
                                                          ↓
                                              text → the chat box
                                                          ↓
                                              audio discarded
```

`core/voice/voice-recorder.ts` holds all of it. The component only reads
signals and calls two methods.

### The recorder's states

`idle` → `requesting` → `recording` → `transcribing` → `idle`

with `error` reachable from any of them. Exposed as a signal so the interface
can show exactly what is happening — "Listening… 0:04" is very different from
"transcribing", and a single spinner for both is confusing.

### Audio format

Browsers disagree. Chrome and Firefox produce WebM with Opus; Safari produces
MP4. `pickSupportedMimeType()` takes the first the browser supports; the
transcription model reads all of them.

Recording settings enable echo cancellation, noise suppression and automatic
gain. These are tuned for speech rather than music and make a noticeable
difference to accuracy in an ordinary room.

### Limits

| Limit             | Value         | Why                                                                                                        |
| ----------------- | ------------- | ---------------------------------------------------------------------------------------------------------- |
| Maximum recording | 120 seconds   | A self-stop, so someone who walks away does not leave the microphone live and then upload an enormous file |
| Maximum upload    | 10 MB         | Bounds server memory                                                                                       |
| Rate limit        | 10 per minute | Transcription is the most processor-intensive thing the server does                                        |

The 120-second stop is enforced in the browser _and_ the duration is checked
again on the server, because a browser limit is a convenience, not a control.

---

## The browser permission flow

A browser will not let a page use the microphone without the user agreeing.

1. The page calls `getUserMedia`.
2. **The browser** shows its own prompt near the address bar. We cannot style
   it, move it, or pre-empt it.
3. The user chooses Allow or Block.
4. On Allow, recording starts and the browser shows a recording indicator for
   as long as the microphone is live.
5. **On Block, the choice is remembered, and asking again does nothing at all.**
   The prompt simply does not reappear.

Step 5 is what confuses people, and why `permissionDenied` is a separate signal
from `error`. When it is set, the interface explains that the browser's own
site settings must be changed:

> Microphone access was blocked. The browser will not ask again, so this has to
> be changed in its own settings: click the icon at the left of the address
> bar, set the microphone to Allow, and reload the page.

Without that explanation the button appears simply broken.

### Every failure, and what the user is told

| Browser error      | What we say                                                      |
| ------------------ | ---------------------------------------------------------------- |
| `NotAllowedError`  | Blocked — change it in the browser's settings, with instructions |
| `NotFoundError`    | No microphone found. Check one is connected                      |
| `NotReadableError` | Another application is using it. Close that and retry            |
| anything else      | Could not start recording. You can still type                    |

Every message ends with a way forward. **Typing always works**, and every voice
failure says so.

### Secure origins

Browsers only allow microphone access on a secure origin: HTTPS in production,
with `localhost` specially exempted so local development works. If voice input
works locally and fails on a deployed site, check the site is on HTTPS — that
is the answer nine times out of ten.

---

## Releasing the microphone

```typescript
this.stream?.getTracks().forEach((track) => track.stop());
```

Every track must be stopped explicitly. If they are not, the browser keeps
showing its recording indicator and **the microphone stays live**. That is both
alarming to the user and a genuine privacy failure — the exact thing this
design exists to prevent, caused by forgetting one line.

`releaseMicrophone()` is called on every path out of recording: normal
completion, cancellation, and failure.

---

## What happens to the transcript

It is put into the message box, **appended** rather than replacing, so a player
can dictate and then correct or add to it by typing before sending. If
`voice_autosend` is on, it sends immediately.

From that point it is an ordinary message: scrubbed of structured personal data
before being sent to Google, and encrypted before being stored.

**The transcript is never logged.** The server records how many bytes of audio
arrived, how many seconds it was, and how many characters came out — never the
words.

---

## The Dungeon Master speaking back

Narration is read aloud by the voice built into the browser
(`SpeechSynthesis`), so **nothing is sent anywhere to produce the audio** — the
text has already been to Google to be written, and speaking it adds no new
disclosure. That is the opposite of the situation with the microphone, and it
is why this direction needs no defending.

### Turning it off

Two controls, because they answer two different questions.

**"Do I want to be read to at all?"** is a toggle, in Settings and repeated as a
chip on the play screen. It is saved **to the account**, so it follows the
person between devices — a preference about them, not about their hardware. The
chip is a shortcut to the same setting rather than a second switch, because two
switches that can disagree is a bug waiting to happen. It appears whenever the
browser can speak at all, not only when it currently is: a control that
disappears when you turn it off cannot be turned back on.

Switching it off also ends hands-free play, which has nothing left to wait for.

**"How loud?"** is a slider, in Settings, saved **to the device**. The same
reasoning as the voice choice above: headphones on a train and laptop speakers
in a quiet room want very different settings, so carrying one number between
machines would be actively unhelpful.

### Zero is not the same as quiet

Dragging the slider to nothing does not speak at zero volume — it skips
speaking entirely and reports itself finished at once.

Speaking silently would still take the full thirty seconds, during which the
status line claims to be reading aloud and hands-free mode refuses to listen
because it is waiting for narration that cannot be heard. Finishing immediately
is what the player actually asked for.

### A trap worth knowing about

`readStoredVolume` reads the slider's saved value, and the obvious way to write
it is wrong:

```ts
const stored = Number(localStorage.getItem(KEY)); // wrong
return Number.isFinite(stored) && stored >= 0 && stored <= 1 ? stored : 1;
```

**`Number(null)` is 0, and so is `Number('')`** — neither is `NaN`. The range
check therefore accepts "nothing has ever been stored" as "turned all the way
down", and the narrator is silent for every new user, with no error to show for
it. Emptiness has to be checked before the conversion. There are tests for both
cases in `speech.spec.ts`, and both were written because the bug happened.

---

## If speech-to-text is unavailable

The libraries are an optional install (`uv sync --extra voice`) because they
are several hundred megabytes. If they are absent the endpoint returns a clear
503 explaining how to enable it, and the interface shows that message.

**Typing is unaffected.** Voice input degrades to absent, never to broken.

---

## Related documents

- [ARCHITECTURE.md](ARCHITECTURE.md) — where the recorder sits.
- [DICE.md](DICE.md) — the other half of the play screen.
- [Backend transcription service](../../backend/app/services/transcription.py) —
  the other half.
- [ADR-008](../../docs/DECISIONS_PRIVACY.md) — the decision and its cost.
