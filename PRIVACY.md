# Security and Data Handling

**Read this when** you need to know how user data is protected, what a breach
would expose, and what is sent to third parties. It is the document to reread
before adding any feature that touches user data.

> **This describes a deliberately conventional security posture**, chosen so
> that one person new to application development can run it without a
> specialist skill set. An earlier version of this project used per-user
> encryption keys managed by AWS KMS. That was removed on purpose — it was more
> machinery than this application warrants, and a lost key would have meant
> permanently unreadable data. What is here now is what a well-built ordinary
> web application does.

---

## What is protected, and how

| Data | How it is protected |
|---|---|
| **Passwords** | Hashed with Argon2id. Never stored, never recoverable, by anyone |
| Email addresses, names | Database access control, TLS in transit, provider disk encryption |
| Campaigns, characters, transcripts | The same |
| Session tokens | Phase 2 stores only a hash, so a leak does not hand over working sessions |
| Everything in transit | TLS between browser and server, and between server and database |

**The one that is genuinely different is the password.** It is stored as a
one-way fingerprint. There is no query, no tool and no amount of time that
turns it back — not for an attacker, and not for you. Everything else is
protected by controlling *who can reach the data*, not by scrambling it.

---

## What a database breach would expose

Being straightforward, because a security document that overstates its
protection is worse than none:

**Readable to anyone who obtains the database:** email addresses, usernames,
display names, campaign titles and premises, character names and backstories,
and every message in every conversation.

**Not readable:** passwords. Those are Argon2id digests, and Argon2id is
deliberately slow and memory-hungry precisely so that a stolen database cannot
be cracked at speed.

**What follows from that.** The database credentials are the thing that matters
most. Treat them like a password to your own email:

- Never commit them. `.env` is in `.gitignore`; check `git status` before
  committing if you are unsure.
- In production they go in `fly secrets set`, never in a config file.
- The database is reachable only from the backend's address, never from the
  open internet.
- The application connects as a user with rights to one database and no
  ability to `DROP` or `ALTER` anything.

---

## Passwords, in detail

**Argon2id**, via `argon2-cffi`, with `time_cost=3`, `memory_cost=65536`
(64 MB), `parallelism=2`.

### Hashing is not encryption, and the difference matters

This is the distinction newcomers most often get wrong, and getting it wrong is
a serious defect rather than a style choice.

- **Encryption is a round trip.** You encrypt, and later you decrypt back to the
  original. It is for data you need to read again.
- **Hashing is one way.** There is no way back. You can only hash a guess and
  see whether the two match.

Passwords are hashed. If they were encrypted, anyone who obtained the key would
recover every password in plaintext — and because people reuse passwords, you
would have handed the attacker their email and bank logins too.

### Why Argon2id rather than something faster

A fast hash is a liability. An attacker with a stolen database tries billions of
guesses per second on specialised hardware. Argon2id is deliberately slow *and*
memory-hungry, and the memory requirement is what defeats that hardware: you can
fit thousands of tiny fast circuits on a chip, but not thousands of copies of
64 megabytes.

**That 64 MB is charged per concurrent login**, so it interacts directly with
the memory size of the server. Worth remembering before raising it.

### Two supporting measures

- **`verify_dummy`** spends the same time when no account matches. Without it,
  an unknown email returns in a millisecond and a known one in 300 — and an
  attacker enumerates your users with a stopwatch.
- **`needs_rehash`** quietly upgrades old hashes at the next sign-in as the
  recommended parameters rise, with no password reset and no announcement.

---

## The other protections

Each of these is standard, and each closes a real category of attack. Full
implementation detail is in
[backend/docs/SECURITY.md](backend/docs/SECURITY.md).

| Protection | Stops |
|---|---|
| **XSRF tokens** | A malicious page making requests as you, using your logged-in session |
| **SSRF allowlist** | Somebody tricking the server into fetching an internal address, such as a cloud credential service |
| **Rate limiting** | Password guessing, account enumeration, and burning the AI quota |
| **Input validation** | Malformed and oversized data reaching application code at all |
| **Security headers** | Clickjacking, content-type confusion, and referrer leakage |
| **TLS everywhere** | Anyone on the network path reading or altering traffic |
| **Ownership checks on every query** | One account reading another's campaigns by guessing an identifier |
| **Random UUID identifiers** | Guessing the next record by counting up from one |
| **Log redaction** | Passwords and tokens ending up in log files |

---

## What is recorded, and what is not

### Logs

Structured JSON, with credential-shaped fields replaced by `<redacted>`.
**Request bodies are never logged.** The rule the codebase follows is *log
identifiers, not contents*: a `user_id` tells you which account without putting
anybody's words in a file that gets copied around.

Every request carries a **correlation identifier**, returned to the browser and
stamped on every log line for that request. When somebody reports a problem you
ask for it and search the logs — that is the intended debugging workflow, and
it is usually faster than reading database rows anyway.

### Analytics

Counts and categories only: sessions started, turns taken, voice versus typing,
error categories, country.

**There is no free-text column anywhere in the analytics table.** Not a
convention — there is physically nowhere for a message to land, so a careless
change later cannot start recording what players typed. Unknown event names are
rejected at write time rather than silently accepted.

Country comes from the edge network's `CF-IPCountry` header, so the server
never inspects or stores an IP address to work out geography.

---

## Third-party data flow: Google Gemini

**This is the one place user data genuinely leaves your control**, and the part
of this document most worth reading.

Every prompt sent to Gemini goes to Google. **Google's free-tier terms are
explicit**: content submitted to the unpaid service is used to provide, improve
and develop Google's products, and human reviewers may read, annotate and
process it. Google says it disconnects that content from your account first,
and advises against submitting sensitive or personal information.

**On the paid tier this changes entirely** — Google states it does not use paid
prompts or responses to improve its products.

Two responses, and only the second is complete:

1. **In-app disclosure.** The "Your data" screen tells users plainly, before
   they type, where their words go and what Google may do with them. People
   cannot make a sensible choice about what to type if they do not know.
2. **Enable billing.** The complete fix, and at this application's traffic it
   costs a few pounds a month. **If real people other than you will use this,
   do it.** See [backend/docs/GEMINI.md](backend/docs/GEMINI.md).

There is also an outbound scrubber that removes email addresses, phone numbers,
card numbers and postcodes from prompts before they are sent
(`SCRUB_OUTBOUND_PROMPTS=true`). It is a reduction, not a guarantee: it cannot
catch a name in an ordinary sentence, because "my sister Emma is coming over"
is indistinguishable from naming a character.

### Voice is different, and does not go to Google

Browsers have built-in speech recognition, and in Chrome it works by streaming
raw microphone audio to Google. This application does not use it. Recordings go
to our own server, are transcribed by a model running there, and are discarded.

The reasoning: text can be reviewed and scrubbed before it is sent. A recording
cannot — it carries the speaker's identity in its waveform whatever the words
are, plus whatever else was audible in the room.

That choice costs about **$4/month** in extra server memory. See
[docs/COSTS.md](docs/COSTS.md).

---

## Account deletion

Deleting an account removes it and everything belonging to it — campaigns,
characters, play sessions and every message — through `ON DELETE CASCADE` in
the schema. Nothing is left behind for a later cleanup job to forget.

Analytics events survive with their `user_id` set to `NULL`, so the totals stay
correct while the events become anonymous.

**One honest limitation:** this does not reach into database backups. A backup
taken before the deletion still contains the rows until it ages out of the
retention window. That is true of essentially every online service, and it
should be stated in any privacy policy you write rather than glossed over.

---

## Known limitations

Every one of these is a deliberate, documented acceptance rather than an
oversight.

1. **Database access means data access.** Anyone who can query the database can
   read emails and conversations. Access control is the protection.
2. **Free-tier prompts are used for training.** Fixed by enabling billing.
3. **The outbound scrubber cannot catch names.** Structured patterns only.
4. **Backups outlive deletion** until they age out.
5. **Authentication is not yet real.** Session tokens are placeholders. The
   backend refuses to start in production while that is true.
6. **DNS rebinding against the SSRF guard.** Narrow, and mitigated by the
   hostname allowlist.

---

## If you later want stronger protection

The obvious next step, should this ever hold data you would be seriously
troubled to lose control of, is encrypting personal columns in the application
before they are written. That protects against a leaked backup or a
compromised database host.

**It is not free**, which is why it is not here:

- An encryption key must be generated, stored and backed up. **If it is lost,
  the data is permanently unreadable and no backup can recover it.**
- Encrypted columns cannot be searched or sorted by the database, so login
  needs a separate searchable fingerprint of the email address, and lists have
  to be sorted after decryption.
- Key rotation becomes a re-encryption job across every row.

That is a reasonable trade for a service holding medical or financial records.
It is a poor one for a Dungeons & Dragons game maintained by one person, where
the most likely outcome is a lost key and lost data.

---

## Related documents

- [backend/docs/SECURITY.md](backend/docs/SECURITY.md) — implementation detail.
- [backend/docs/GEMINI.md](backend/docs/GEMINI.md) — what Google does with
  prompts.
- [ARCHITECTURE.md](ARCHITECTURE.md) — how the pieces fit together.
- [docs/LOCAL_MYSQL.md](docs/LOCAL_MYSQL.md) — see your own data, including
  what a password hash looks like.
