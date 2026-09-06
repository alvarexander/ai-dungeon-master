# Architecture Decisions — Security and Data

**Read this when** you want to know why user data is handled the way it is.
For framework and hosting decisions, read
[Architecture Decisions — Platform](DECISIONS_PLATFORM.md). The index of all
decisions is in [ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md).

---

## How to read this file

Each decision has five parts: **the question**, **the decision**, **why**,
**what was rejected**, and **cost to reverse** — cheap, moderate, or expensive.
New terms are defined the first time they appear; if one still puzzles you,
check the [Glossary](GLOSSARY.md).

---

## ADR-002 — Conventional security, not application-layer encryption

**The question.** How much protection should personal data get in the database?

**The decision.** The protection a well-built ordinary web application uses:
hashed passwords, access control, TLS in transit, a firewalled database, and
the hosting provider's encryption of the underlying disks. **Personal data is
stored as readable values.**

**Why.** This project is maintained by one person new to application
development, and every security control has a running cost in attention as well
as in money. The controls above cost almost nothing to operate: they are
configured once and then they work.

Application-layer encryption is a different proposition. An earlier version of
this project used per-user keys wrapped by AWS Key Management Service, and it
was removed deliberately. The reasons are worth recording, because the idea is
tempting and the costs are not obvious until you own them:

- **A key that must never be lost.** If the encryption key is lost, every
  encrypted value is permanently unreadable and no backup can recover it. For a
  solo maintainer that is a realistic way to destroy all the data, and it has
  no undo.
- **Encrypted columns cannot be searched or sorted.** Login needs a separate
  searchable fingerprint of the email address. Campaign lists cannot be ordered
  by title in the database. Each of those is a workaround someone must
  understand before they can change anything.
- **Key rotation becomes a migration** across every row, rather than a setting.
- **It protects against one specific attacker** — someone who obtains the
  stored data but not the running server. Real, but not the most likely
  failure for a hobby project, which is far more likely to be a leaked
  credential or a mistake in code.

**What was rejected.**

- **Per-user keys wrapped by AWS KMS.** The strongest option. It also required
  an AWS account, a key policy, cross-cloud identity federation, and an
  understanding of envelope encryption before anyone could change a field. Too
  much machinery for what this application holds.
- **A single application key in an environment variable.** Much simpler, and it
  genuinely would protect a leaked backup. Rejected for the lost-key risk
  above: a beginner losing one env var should not be able to destroy every
  account irrecoverably.

**Be clear about what this costs.** Anybody who can query the database can read
email addresses and conversations. If this application ever holds something
genuinely sensitive, revisit this decision — [PRIVACY.md](../PRIVACY.md) has a
section on what adding encryption would involve.

**Cost to reverse.** Moderate. Adding encryption later means a migration to
convert columns and a script to encrypt existing rows.

---

## ADR-003 — Passwords are hashed with Argon2id, never encrypted

**The question.** How are passwords stored?

**The decision.** **Argon2id**, via `argon2-cffi`.

**Why, and why the distinction matters.** This is exactly where newcomers go
wrong, so it is worth being slow.

- **Encryption is a round trip.** You encrypt, and later decrypt back to the
  original. It is for data you need to read again.
- **Hashing is a one-way street.** There is no way back. You can only hash a
  guess and see whether the two match.

A password should never be readable — not by an attacker, not by the database,
not by you. So it is hashed. If passwords were encrypted, anyone obtaining the
key would recover every password in plaintext, and because people reuse
passwords you would have handed over their email and bank logins too. Encrypted
passwords are a serious defect, not a stylistic choice.

**Why Argon2id specifically.** A fast hash is a liability: an attacker with a
stolen database tries billions of guesses per second on specialised hardware.
Argon2id is deliberately slow *and* memory-hungry, and the memory requirement
is what defeats that hardware. It won the Password Hashing Competition in 2015
and is the current OWASP recommendation.

**Note this is the one control kept at full strength** even though everything
around it was simplified. That is deliberate: it costs nothing to operate, and
it is the difference between a database leak being embarrassing and being
catastrophic for users who reuse passwords elsewhere.

**Cost to reverse.** Not applicable. You cannot turn hashes back into
passwords, which is the point.

---

## ADR-004 — Analytics has no free-text column

**The question.** How do you collect useful usage numbers without accumulating
a record of what people wrote?

**The decision.** The analytics table accepts only enumerated values, numbers,
booleans and timestamps. **There is no free-text column anywhere in it.**

**Why this is a mechanism rather than a promise.** A rule saying "do not put
message content in analytics" depends on everybody remembering. A schema with
nowhere to put it does not. A careless change later cannot smuggle a player's
words in, because there is physically no column for them.

Unknown event names are rejected at write time and raise an error, rather than
being dropped silently — so the mistake surfaces during development instead of
becoming a permanent gap in the data.

Geography is country only, taken from the edge network's header, so the server
never inspects or stores an address to work it out.

**What was rejected.** A general `properties` JSON blob, which is what most
analytics libraries offer. It is convenient and it is exactly the hole this
decision closes.

**Cost to reverse.** Cheap to widen, and you should not.

---

## ADR-005 — Deletion removes the data

**The question.** What happens when someone deletes their account?

**The decision.** The row is deleted, and `ON DELETE CASCADE` in the schema
takes campaigns, characters, sessions and messages with it. Analytics events
survive with their `user_id` set to `NULL`.

**Why cascades rather than cleanup code.** A cleanup routine that deletes six
tables in order is a routine somebody can forget to update when a seventh table
is added. The database enforcing it means orphaned rows cannot happen.

**Why analytics survive.** The totals are what the product is measured by, and
they should not drop retroactively every time somebody closes their account.
Setting the identifier to `NULL` keeps the count and removes the person.

**The honest limitation:** this does not reach into backups. A backup taken
before the deletion still contains the rows until it ages out. That is true of
essentially every online service and should be stated in any privacy policy
rather than glossed over.

**Cost to reverse.** Cheap.

---

## ADR-006 — Correlation identifiers for debugging

**The question.** How do you investigate a fault somebody reports?

**The decision.** Every request gets a random identifier, returned to the
browser in a header, shown on error screens, and stamped on every log line for
that request.

**Why.** The user quotes it, you search the logs, and you see the entire life of
that one request. It is faster than finding their account and reading rows, it
works even when you do not know who they are, and it does not involve reading
anybody's conversations to fix a bug that has nothing to do with their content.

A supplied identifier is accepted only if it is short and alphanumeric —
otherwise an attacker could inject newlines and forge log lines.

**Cost to reverse.** Cheap, and there is no reason to.

---

## ADR-007 — Rate limiting

**The question.** How do you stop password guessing, account enumeration, and
somebody burning the AI quota?

**The decision.** Per-scope limits, counted per caller, enforced before the
endpoint body runs. The strictest is sign-in: five attempts per fifteen
minutes.

**Why those numbers.** Each one is reasoned rather than round:

- **Sign-in, 5 per 15 minutes.** Makes password guessing impractical, while
  leaving room for a person who mistypes three times.
- **Registration, 3 per hour.** Registration reveals whether an email is
  already in use, so it is the other enumeration surface. Also stops automated
  signups burning the AI quota.
- **Chat, 20 per minute.** Far above natural play, well below what would
  exhaust a daily AI allowance in one sitting.
- **Speech to text, 10 per minute.** Transcription is the most
  processor-intensive thing the server does.

Limits are declared as dependencies on the endpoint, so an endpoint that
declares one cannot accidentally skip it — the check runs before its body.

**One thing to know before scaling.** The current limiter counts in one
process's memory. Two machines keep separate tallies, silently doubling every
limit. Move the counters to the database before running more than one machine.

**Cost to reverse.** Cheap.

---

## ADR-008 — Server-side speech-to-text, not the browser's Web Speech API

**The question.** Players want to speak to the Dungeon Master. How is speech
turned into text?

**The decision.** The browser records audio and uploads it to our backend,
which transcribes it locally with **faster-whisper**, an efficient
implementation of OpenAI's open-source Whisper model that runs on an ordinary
processor. The audio never leaves infrastructure we control.

**Why not the obvious option.** The browser's built-in Web Speech API looks
free and takes five lines of code. But in Chrome it **streams the raw
microphone audio to Google's servers** — a recording of the user's voice, in
their home, with whatever else is audible in the room.

**Why this survived the simplification.** Everything else here was made more
conventional, and this was not. The reason: text and audio are genuinely
different. Text can be reviewed, scrubbed of addresses, and reasoned about. A
voice recording cannot be scrubbed — it carries the speaker's identity in its
waveform whatever the words are. Sending text to Google is a considered
trade-off that the interface discloses; sending audio would be an unbounded one.

**What this costs you.** Real money, and it is the clearest example in the
project of a control with a price tag. Transcription is computation, and it
happens on your server rather than Google's. The Whisper `base` model needs
roughly 1 GB of memory, which moves the Fly.io machine from the smallest size
to a 1 GB instance — about **$4–5/month**. See [Costs](COSTS.md).

**Cost to reverse.** Cheap technically. The transcription service sits behind
an interface with one implementation.
