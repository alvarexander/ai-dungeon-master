# Privacy

**Read this when** you need the whole privacy picture in one place: what is
being defended against, how every field is classified, what a breach would
actually expose, who holds which keys, and what the design costs to operate.

This is the document to reread before adding any feature that touches user
data.

---

## The threat model

**The adversary:** someone with full read access to the MySQL database. A
leaked RDS snapshot, a stolen backup, a compromised read replica, a rogue
database administrator, or you on a bad day.

**The requirement:** that adversary learns nothing about who the users are.

**The rule, stated as plainly as it can be:** in a database dump, the only
human-meaningful plaintext is the username. Everything else identifying is
ciphertext or an irreversible digest.

### What is explicitly outside the boundary

Two things, stated here rather than implied, because a security claim with
unstated exceptions is not a claim:

- **The running application server**, which necessarily holds keys while it is
  working.
- **The AWS KMS keys it can call.**

Compromising the database *and* a live server is a different and much harder
attack. This design does not defend against it, and does not pretend to.

Also outside: anything already sent to Google Gemini. Once a prompt leaves, it
is subject to Google's terms rather than ours. See "Third-party data flow".

---

## What counts as personal data here

**Personal data:** email, phone number, first name, last name, date of birth,
IP address, payment details, and **any free text a user typed**.

That last clause is the one that surprises people, and it is doing most of the
work. Campaign titles, character names, backstories and every message in every
conversation are personal data — because players type their own names, their
friends' names, where they live, and what happened at work into free text.

**Not personal data, by explicit decision:** username and display name. These
are stored readable, and the interface says so at the point of entry so that
someone choosing a handle knows it will be visible.

---

## Data classification

Every column in the schema is exactly one of four things, declared in a SQL
`COMMENT` so the classification lives in the database and cannot drift from the
documentation.

| Class | Meaning | Readable from a dump? | Searchable? |
|---|---|---|---|
| **PLAINTEXT** | As written | Yes | Yes |
| **ENCRYPTED** | AES-256-GCM under a per-user key | No | No |
| **HASHED** | One-way digest | No | Only by comparing a guess |
| **BLIND-INDEX** | Keyed one-way fingerprint, stable | No | Yes, exact matches |

The full per-column table is in
[backend/docs/DATABASE.md](backend/docs/DATABASE.md). A summary of where the
line falls:

| Data | Class | Why |
|---|---|---|
| Username, display name | PLAINTEXT | Explicitly non-personal here |
| Identifiers, timestamps, counters | PLAINTEXT | Opaque or non-identifying |
| Character class, level, campaign tone | PLAINTEXT | Fixed values; identify nobody. Keeping them readable means aggregate questions need no decryption |
| Email | ENCRYPTED **and** BLIND-INDEX | Encrypted for storage; fingerprinted so login can find it |
| Phone, names, date of birth | ENCRYPTED | Directly identifying |
| Campaign titles, premises | ENCRYPTED | User free text |
| Character names, backstories, sheets | ENCRYPTED | User free text |
| **Every message in every transcript** | ENCRYPTED | User free text |
| Password | HASHED (Argon2id) | Must never be readable by anyone |
| Refresh tokens | HASHED | A leak must not hand over working sessions |
| IP addresses | HASHED, daily salt | Personal data; only ever needed as a counting key |
| Support access reasons | ENCRYPTED under a **separate audit key** | So shredding a user does not erase the record of who read their data |

---

## Breach exposure inventory

If the entire database were published tomorrow, this is exactly what would be
in it.

### Readable

- **Usernames and display names.** If someone chose their real name as a
  display name, that is their disclosure — made with the interface telling them
  it would be visible.
- **How many accounts exist and when each was created.**
- **Activity shape:** how many campaigns, how many messages, how long each
  message was, whether it was typed or spoken, which character class, which
  campaign tone, which ruleset.
- **That two accounts share an email address** — from equal blind index values —
  without learning what the address is.

### Not readable, at all

Email, phone, first name, last name, date of birth, IP addresses, campaign
titles, campaign premises, character names, backstories, character sheets, and
every word of every conversation.

There is no computational attack on these. The keys are not in the database and
are not derivable from anything in it.

### What an attacker could still do

Being honest about the residual risks:

- **Correlate activity within the dump.** They can see that one account played
  a great deal in August. They cannot tell whose account it is.
- **Test guessed email addresses — but only if they also stole the blind index
  key**, which lives in a different system entirely. This is why that key's
  separation is the whole defence.
- **Try the live application.** The login endpoint is the remaining enumeration
  surface, which is why it returns identical responses either way and is rate
  limited to five attempts per fifteen minutes.

---

## Key custody

| Key | Purpose | Lives | In the database? |
|---|---|---|---|
| KMS master key | Wraps every per-user key | AWS KMS hardware | **Never** |
| Per-user data key | Encrypts one user's data | Wrapped, in their row | Only wrapped |
| Blind index key | Fingerprints emails | AWS Secrets Manager | **Never** |
| IP salt | Fingerprints addresses; rotates daily | Derived in memory | **Never** |
| Audit key | Encrypts support access reasons | A separate KMS key | **Never** |

### Your administrator role cannot read user data

The KMS key policy grants `Decrypt` on the user data key to the **application
role only**. Your everyday IAM administrator role is explicitly denied it.

This is deliberate and it is inconvenient on purpose. It means that if your own
AWS credentials are phished, the attacker gets your infrastructure but not your
users' data.

### Break-glass

A separate role that *can* decrypt, for a genuine emergency:

1. Assuming it requires multi-factor authentication and a stated reason.
2. Every use fires a CloudTrail alert immediately.
3. Every use is reviewed afterwards.
4. The grant is time-boxed.

**It should be used approximately never.** If you find yourself reaching for it
routinely, the debugging workflow below is not working and that is the thing to
fix.

### What you do instead of reading the table

This makes production debugging genuinely harder, and here is the workflow that
replaces it:

1. **Ask for the correlation identifier.** Every error screen shows one. It
   finds every log line for that request.
2. **Read the metrics.** Latency, token counts, finish reasons, error codes and
   retry counts are all recorded, and answer most questions on their own.
3. **Ask the user to switch on debug capture** and reproduce. Their prompt and
   the reply are stored, encrypted under their own key, for 48 hours.
4. **Only then, an audited support grant** — which the user is told about.

A worked example is in
[backend/docs/OBSERVABILITY.md](backend/docs/OBSERVABILITY.md).

---

## Retention and deletion

| Data | Kept for | Then |
|---|---|---|
| Account and campaigns | Until deleted | Crypto-shredded |
| Debug telemetry (logs) | 14 days | Hard deleted |
| Raw analytics events | 90 days | Hard deleted |
| Aggregate counters | Indefinitely | Never identify anyone |
| Opt-in debug captures | 48 hours maximum | Hard deleted |
| Support access audit | Indefinitely | Append-only |

### Crypto-shredding

Deleting an account **destroys the encryption key** rather than the data.

It sounds like sleight of hand, so here is the mechanism. Every piece of that
user's data is encrypted with their key, and their key exists in exactly one
place: the wrapped copy in their row. Delete those bytes and the ciphertext
everywhere else — live tables, last night's snapshot, the backup from March, a
copy an attacker exfiltrated last week — becomes permanently unreadable.

Not hidden. Not flagged deleted. Mathematically unrecoverable, by us and by
anyone else, forever.

This is why the design uses a key per user rather than one key for everything,
and it is the single most valuable property of that choice. It is also the only
honest way to answer "delete my data" when backups exist that nobody can edit.

The account-deletion endpoint destroys the key, severs the analytics link, and
leaves the ciphertext to be cleaned up lazily.

---

## Observability without surveillance

Two planes that never join:

**Analytics.** Pseudonymous, aggregate, long retention. Every user has a random
`analytics_id` unrelated to their account, linked only through one encrypted
mapping row. **The analytics schema has no free-text column anywhere**, so
nothing a user typed can reach it — not by accident, not by a careless change.
Geography is country only, taken from an edge header so no address is ever
inspected. Durations are bucketed so an exact value cannot act as a
fingerprint.

**Debug telemetry.** Per-request, 14 days. Every request has a correlation
identifier stamped on every log line and returned to the browser. Logs use an
**allowlist**: a field not explicitly declared safe is replaced with a
description of its type and length. A blocklist would protect only against the
leaks somebody already thought of.

Full detail in
[backend/docs/OBSERVABILITY.md](backend/docs/OBSERVABILITY.md).

---

## Third-party data flow

**Every prompt sent to Gemini leaves your infrastructure.** This is the one
place personal data leaves your control by design.

**Google's free tier terms are explicit:** content submitted to the unpaid
service is used to provide, improve and develop Google's products, and human
reviewers may read, annotate and process it. Google says it disconnects that
content from your account first, and advises not to submit sensitive,
confidential or personal information.

**On the paid tier this changes entirely** — Google states it does not use paid
prompts or responses to improve its products.

Three responses, and only the third is complete:

1. **Outbound scrubbing.** Emails, phone numbers, card numbers, postcodes,
   links and dates of birth are replaced before sending. **What it cannot catch
   is a name in an ordinary sentence** — "my sister Emma is coming over" is
   indistinguishable from naming a character. An earlier version that stripped
   all capitalised words made the Dungeon Master incoherent, and a privacy
   control that ruins the product gets switched off.
2. **In-app disclosure.** The "Your data" screen tells users plainly, before
   they type, that their words go to Google and what Google may do with them.
3. **Enable billing.** The complete fix. At this application's traffic it costs
   pennies a month. **If real people other than you will use this, do it.**

**Audio is different and never goes to Google.** See ADR-008.

---

## Known limitations

Every one of these is a deliberate, documented acceptance rather than an
oversight.

1. **A live server compromise defeats this.** The server holds keys while
   working. Out of scope, and a much harder attack.
2. **The blind index leaks equality.** Two accounts with the same email are
   visible as such. The address is not.
3. **The scrubber cannot catch names.** Structured patterns only.
4. **Free-tier prompts are used for training.** Fixed by enabling billing.
5. **Analytics timing correlation.** Someone with the analytics table and
   external knowledge of when a specific person played could make a probabilistic
   link. Mitigated by bucketing and by country-only geography.
6. **DNS rebinding against the SSRF guard.** Narrow, and mitigated by the
   hostname allowlist.
7. **Phase 1 has no real authentication.** The application refuses to run this
   way in production.

---

## What this design costs

**Things you cannot do:**

- Search transcripts. Not for support, not for moderation, not for analytics.
- Sort campaigns by title in the database — it happens after decryption, which
  is why lists are paged.
- Look up a user by email address in a database client.
- Read a user's data to debug their problem.
- Recover anything for a user who deleted their account. Ever.

**Things it costs in money and effort:**

- A KMS call per user per five minutes (cached), and its small AWS bill.
- Extra memory on the backend for local transcription: about $5/month.
- Slower development, because every new field requires a classification
  decision.

**What you get:**

A database breach exposes usernames and timestamps. That is the entire
incident. No email addresses to sell, no transcripts to publish, no disclosure
letter describing what was in them, and no lasting exposure for anybody who had
already deleted their account.

---

## Related documents

- [ARCHITECTURE.md](ARCHITECTURE.md) — diagrams of the boundary.
- [docs/DECISIONS_PRIVACY.md](docs/DECISIONS_PRIVACY.md) — why each choice.
- [backend/docs/SECURITY.md](backend/docs/SECURITY.md) — the implementation.
- [backend/docs/DATABASE.md](backend/docs/DATABASE.md) — per-column detail.
- [backend/docs/GEMINI.md](backend/docs/GEMINI.md) — what Google does with prompts.
