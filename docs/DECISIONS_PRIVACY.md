# Architecture Decisions — Privacy and Data

**Read this when** you want to know why user data is stored the way it is: the
encryption scheme, how login finds an account without reading email addresses,
how deletion works, and how telemetry avoids collecting people. For framework
and hosting decisions, read
[Architecture Decisions — Platform](DECISIONS_PLATFORM.md). The index of all
decisions is in [ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md).

## How to read this file

Each decision has five parts:

- **The question** — what had to be decided.
- **The decision** — what was chosen.
- **Why** — in plain language.
- **What was rejected** — the roads not taken, and why they were worse.
- **Cost to reverse** — cheap, moderate, or expensive. "Expensive" means it
  would take days of work and might require rewriting stored data.

New terms are defined the first time they appear. If a term still puzzles you,
check the [Glossary](GLOSSARY.md).

---

## ADR-002 — Encryption strategy: application-layer envelope encryption

**The question.** Your threat model assumes an attacker reads the entire
database. How do you store an email address such that reading the database
teaches the attacker nothing?

**The decision.** *Envelope encryption* performed by the application, using a
separate encryption key for every user.

Here is the shape of it, in plain language. Think of each user's personal data
as papers in a locked box. The key to that box is the user's **Data Encryption
Key** (DEK). If we stored that key next to the box, an attacker who steals the
box also steals the key — useless. So instead, we lock the *key itself* inside a
second, smaller box, and only Amazon's Key Management Service (KMS — a hardware
vault run by AWS that holds keys and never hands them out) can open that second
box. The locked-up key is called a **wrapped DEK**, and it is stored in the
database next to the user's row. That is the "envelope": a key inside an
envelope, sitting beside the data it opens.

An attacker with a full database dump gets: ciphertext, plus a wrapped key they
cannot unwrap without calling AWS KMS as our application role. They learn
nothing.

The encryption algorithm is **AES-256-GCM**. AES-256 is the standard symmetric
cipher (the same key encrypts and decrypts); GCM is a mode that also detects
tampering, so an attacker cannot flip bits in the ciphertext to corrupt the
result silently.

Each encryption binds *additional authenticated data* (AAD) naming the user, the
table, and the column. AAD is extra context mixed into the tamper check but not
stored in the ciphertext. Practical effect: an attacker who copies the encrypted
email from user A's row into user B's row produces a value that fails to decrypt
rather than one that silently succeeds.

**What was rejected.**

- **MySQL's built-in encryption at rest.** *Encryption at rest* means the disk
  files are encrypted. This defends against someone stealing the physical disk.
  It does nothing against your stated threat: the database server holds the keys
  and decrypts transparently for anyone who can run a `SELECT`. A leaked
  snapshot restored by the attacker decrypts itself. It is worth turning on
  anyway — it is free and defends a different attack — but it is not the answer.
- **One encryption key for the whole application.** Simpler, but then deleting a
  single user's data means finding and overwriting every row they touched,
  including inside backups you cannot reach. Per-user keys make deletion a
  single act (see ADR-005).
- **Encrypting inside the ORM or a database trigger.** An *ORM* (Object
  Relational Mapper) is the library that turns database rows into Python
  objects. If encryption happens inside or below it, then plaintext has already
  travelled to the database server before being encrypted, and it will show up
  in query logs and slow-query logs. Encryption happens *above* the ORM, in the
  repository layer, so the ORM only ever sees ciphertext.

**Cost to reverse.** Expensive. Changing this means decrypting and re-encrypting
every row, and the whole privacy story depends on it.

---

---

## ADR-003 — Email lookup: keyed blind index

**The question.** Login needs to find a user by email address. But the email is
encrypted, and encrypting the same text twice with AES-GCM produces two
different ciphertexts (deliberately — that is what stops an attacker spotting
that two users share an address). So `WHERE email_ciphertext = ?` can never
match. How does login work at all?

**The decision.** A **blind index**: a second column holding
`HMAC-SHA256(index_key, normalize(email))`.

An *HMAC* is a keyed fingerprint. Feed it the same email and the same secret key
and it always produces the same 32 bytes; change either and the output is
unrecognisably different. Because it is deterministic, we can put a unique index
on the column and look up a login in one fast query. Because it is one-way and
keyed, the fingerprint cannot be turned back into an email address — and unlike
a plain hash, an attacker cannot even guess-and-check, because they do not have
the key. The key lives in AWS Secrets Manager, **never in the database**.

`normalize()` lowercases and trims the address, so `Alex@Example.com ` and
`alex@example.com` resolve to the same account.

**What this leaks, precisely.** Two things, and it is important to be exact:

1. **Equality.** An attacker sees that two rows have the same fingerprint, so
   they learn two accounts share an email — without learning which email.
2. **Existence, but only if they already have the key.** Without the index key,
   an attacker holding a database dump cannot test whether `alex@example.com` is
   registered. With the key, they could test any address they can guess. This is
   why the key's absence from the database is the entire defence, and why the
   key must never be logged, committed, or copied into a spreadsheet.

The remaining exposure is *through the live application*: a login endpoint that
says "no such user" for unknown addresses and "wrong password" for known ones
lets an attacker enumerate your users one guess at a time. Two mitigations, both
implemented: the login endpoint returns an identical response either way, and
login is rate limited far more strictly than anything else (see ADR-007).

**What was rejected.** *Deterministic encryption* of the email — encrypting so
the same input always gives the same output — permits the same lookup but is
reversible if the key leaks, whereas an HMAC is one-way even then.

**Cost to reverse.** Moderate. Rotating the index key requires recomputing every
fingerprint, which needs the plaintext emails, which needs a decrypt pass.

---

---

## ADR-004 — Passwords are hashed, never encrypted

**The question.** How are passwords stored?

**The decision.** **Argon2id**, with the `argon2-cffi` library.

**Why, and why the distinction matters.** This is the exact place where
newcomers go wrong, so it is worth being slow.

- **Encryption is a round trip.** You encrypt, and later you decrypt back to the
  original. It is for data you need to read again — like an email address you
  must display on a settings page.
- **Hashing is a one-way street.** You hash, and there is no way back. You can
  only take a guess, hash the guess, and see whether the two hashes match.

A password should never be readable — not by an attacker, not by the database,
not by you. So it is hashed. When someone logs in, we hash what they typed and
compare fingerprints. Nobody ever recovers the original.

If passwords were encrypted, anyone who obtained the key would recover every
password in plaintext — and because people reuse passwords, you would have
handed the attacker your users' email and bank logins too. Encrypted passwords
are a serious security defect, not a stylistic choice.

**Why Argon2id specifically.** A fast hash is a liability: an attacker with a
stolen database tries billions of guesses per second. Argon2id is deliberately
slow *and* deliberately memory-hungry, which defeats the specialised
password-cracking hardware that makes short work of older schemes. It won the
Password Hashing Competition in 2015 and is the current recommendation of OWASP
(the Open Web Application Security Project, the widely-followed authority on web
security). The "id" variant blends the two Argon2 modes to resist both
side-channel and brute-force attacks.

**Cost to reverse.** Cheap in one direction only — you can upgrade the
parameters transparently when users next log in. You can never turn hashes back
into passwords, which is the point.

---

---

## ADR-005 — Deletion by crypto-shredding

**The question.** When a user deletes their account, how do you erase data that
also lives in nightly backups you cannot edit?

**The decision.** Destroy the user's wrapped Data Encryption Key. Do not attempt
to erase the data itself.

**Why this works.** It sounds impossible, so here is the mechanism. Every piece
of that user's personal data is encrypted with their DEK, and their DEK exists in
exactly one place: the wrapped copy in their row. Delete those bytes and the
ciphertext everywhere else — live tables, last night's snapshot, the backup from
March, the copy an attacker exfiltrated last week — becomes permanently
unreadable noise. Not "hidden". Not "flagged deleted". Mathematically
unrecoverable, by us and by anyone else, forever.

This is the single most valuable property of per-user keys, and it is why
ADR-002 chose them.

The account-deletion endpoint therefore does three things: destroys the wrapped
DEK, deletes the row linking the user to their analytics identity (severing
their history into anonymous aggregate — see ADR-006), and leaves the ciphertext
in place to be cleaned up lazily.

**Cost to reverse.** Not applicable, and that is the feature.

---

---

## ADR-006 — Two separate telemetry planes

**The question.** You want to know how the product is used, and you want to be
able to debug faults. Both normally involve collecting data about people.

**The decision.** Two separate systems that never join to each other.

- **Analytics plane.** Every user has an `analytics_id` — a random identifier
  with no mathematical relationship to their `user_id`. The mapping between the
  two lives in one encrypted table. Analytics tables reference only the
  `analytics_id`. Crucially, deleting that one mapping row does not delete the
  analytics; it *orphans* them, turning a person's history into an anonymous
  contribution to the totals. So crypto-shredding a user preserves your business
  metrics while destroying the link to them.
- **Debug plane.** Every request gets a `correlation_id`, returned to the
  browser in a response header and stamped on every log line for that request.
  When a player reports a problem you ask for that identifier. This is the
  primary debugging tool — not reading database rows.

**The hard rule that makes this safe.** The analytics schema has **no free-text
column anywhere**. Fields are enums, booleans, numbers, timestamps. Unknown
fields are rejected at write time, loudly, rather than accepted and dropped.
This means a careless future change cannot smuggle a player's typed message into
analytics, because there is physically nowhere for it to land.

**Cost to reverse.** Moderate now, expensive later. Aggregate counters cannot be
backfilled after users are crypto-shredded — the data is genuinely gone. This is
why the counters are defined up front and err toward collecting more
*aggregates* while collecting fewer *records*.

---

---

## ADR-007 — Rate limiting on hashed identifiers

**The question.** Rate limiting means counting requests per user or per network
address. But addresses are personal data and must not be stored in plaintext.
Does abuse prevention force a hole in the privacy design?

**The decision.** No. Limits are counted against **HMAC fingerprints** of the IP
address and username, never the values themselves.

An *IP address* is the number identifying a device's connection to the internet;
it is personal data under GDPR because it frequently identifies a household. The
fingerprint uses a salt that rotates every day and is never written down next to
the fingerprints, so yesterday's records cannot be matched against today's — a
counter that works for the hour it needs to and is useless as a tracking history
afterwards.

The important consequence: **the entire abuse-prevention path runs without a
single decryption call.** Comparing fingerprints needs no key and no plaintext.
Privacy and security do not trade off against each other here.

**Cost to reverse.** Cheap.

---

---

## ADR-008 — Server-side speech-to-text, not the browser's Web Speech API

**The question.** Players want to speak to the Dungeon Master. How is speech
turned into text?

**The decision.** The browser records audio and uploads it to our backend, which
transcribes it locally using **faster-whisper**, an efficient implementation of
OpenAI's open-source Whisper model that runs on an ordinary processor. The audio
never leaves infrastructure we control.

**Why not the obvious option.** The browser's built-in Web Speech API looks free
and takes five lines of code. But in Chrome it **streams the raw microphone
audio to Google's servers** for transcription. That places a recording of your
user's voice — in their home, possibly with family audible in the background —
outside the encryption boundary this entire design exists to maintain. It is
precisely the leak the boundary is meant to prevent, and no amount of encrypting
the database afterwards compensates for it.

**A note on a tempting new option.** Google now offers a dedicated speech model
(`gemini-3.5-transcribe`) through the same API we already use for the Dungeon
Master. It was considered and rejected for the same reason: it is a third party
receiving raw audio.

**The honest tension.** We do send the *transcribed text* to Gemini, because
that is the product. So why fight over the audio? Because the two are not
equivalent. Text can be scrubbed of names before it is sent, inspected, logged,
and reasoned about. A voice recording cannot be scrubbed — it carries the
speaker's identity in its waveform, plus whatever is audible in the room. Text
is a controllable leak; audio is not.

**What this costs you.** Real money, and this is the clearest example in the
project of a privacy control with a price tag. Transcription is computation, and
that computation has to happen on your server instead of Google's. The Whisper
`base` model needs roughly 1 GB of memory and a second or two of processor time
per utterance. In practice that means the Fly.io machine goes from the smallest
size (256 MB, about $2/month) to a 1 GB instance at roughly **$6–8/month**. See
[Costs](COSTS.md) for the full picture. You are paying about five dollars a month
to keep your users' voices out of Google's hands.

**Cost to reverse.** Cheap technically, expensive ethically. The transcription
service sits behind an interface with one implementation; swapping it is a small
change. Choosing to do so would be a decision to abandon the boundary.

---
