# Glossary — shared terms

**Read this when** a word in any document in this project means nothing to you.
This file covers terms used across both repositories. Each repository also has
its own glossary for terms specific to it:
[backend](../backend/docs/GLOSSARY.md), [frontend](../frontend/docs/GLOSSARY.md).

Terms are grouped by subject rather than alphabetically, because related ideas
are much easier to understand together.

---

## The web, generally

**API (Application Programming Interface)** — a way for one program to ask
another program to do something. Where a person uses a web page, a program uses
an API. Ours is a set of web addresses the Angular app sends requests to.

**Endpoint** — one specific address the API answers on, together with the
method used to reach it. `POST /api/v1/chat/turn` is an endpoint.

**Request and response** — a request is what the browser sends; a response is
what comes back. Every interaction is one of each.

**HTTP method** — the verb of a request. `GET` reads something and must change
nothing. `POST` creates. `PATCH` changes part of something. `DELETE` removes.
The distinction matters: methods that only read are exempt from cross-site
request forgery checks, precisely because they change nothing.

**Status code** — a number describing how a request went. 200 succeeded, 201
created something, 401 not authenticated, 403 refused, 404 not found, 422 the
submitted data was unacceptable, 429 too many requests, 500 the server broke,
502 something the server depends on broke.

**Header** — a labelled piece of information attached to a request or response,
separate from the body. Our API key travels in a header rather than a URL,
because headers are not recorded in access logs or browser history.

**Origin** — the combination of scheme, host and port: `https://app.example.com`
is one origin, `https://api.example.com` another. Browsers treat different
origins as different, mutually distrustful websites.

**CORS (Cross-Origin Resource Sharing)** — the browser rule that a page from one
origin may not read responses from another unless that other origin explicitly
permits it. Because our app and API are on different origins, the backend must
name the frontend or every request is blocked. The rule exists so that a
malicious page cannot silently read your webmail in the background.

**DNS (Domain Name System)** — the internet's address book, translating
`example.com` into a numeric address.

**TLS, and HTTPS** — TLS encrypts data in transit so that nobody between the two
ends can read or alter it. HTTPS is HTTP over TLS. The `s` is TLS.

**HSTS (HTTP Strict Transport Security)** — a header telling a browser to refuse
plain HTTP to this host in future, closing the moment of exposure before a
redirect happens.

**Static files** — files a web server hands over unchanged: HTML, CSS,
JavaScript, images. Our Angular app builds to these, which is why it can be
hosted somewhere that runs no program of its own.

---

## Security

**Authentication** — proving who you are. **Authorisation** — what you are then
allowed to do. Signing in is authentication; being refused someone else's
campaign is authorisation.

**XSRF / CSRF (Cross-Site Request Forgery)** — an attack where a malicious page
causes your browser to send a request to a site you are logged in to, relying on
the browser attaching your cookies automatically. The defence is a token the
attacker's page cannot read. See the
[backend security document](../backend/docs/SECURITY.md).

**SSRF (Server-Side Request Forgery)** — an attack where somebody persuades your
*server* to make a request on their behalf, typically to an address only the
server can reach, such as a cloud provider's internal credential service.

**XSS (Cross-Site Scripting)** — an attack where somebody gets their code to run
inside your page, usually by submitting text that gets displayed without being
escaped. Angular escapes by default, which is why it is not a constant worry
here.

**Encryption** — scrambling data so that only a holder of the key can read it.
Reversible by design: you encrypt, then later decrypt.

**Hashing** — a one-way transformation. You cannot get the original back; you
can only hash a guess and compare. Passwords are hashed, never encrypted. **This
distinction is the one newcomers most often get wrong**, and getting it wrong is
a serious defect rather than a style choice.

**Salt** — random data mixed into each password before hashing, so that two
people with the same password get different results and cannot be attacked
together.

**Argon2id** — the password hashing algorithm used here. Deliberately slow and
memory-hungry, which defeats the specialised hardware attackers use.

**AES-256-GCM** — the encryption algorithm used here. AES-256 scrambles; GCM
additionally detects tampering, so an altered value fails loudly instead of
decrypting to nonsense.

**Nonce** — "number used once". A value included in each encryption so that
encrypting the same text twice gives different results. Not secret, but never
reused with the same key.

**HMAC** — a keyed fingerprint. Same input and key give the same output every
time, but the input cannot be recovered, and without the key nobody can even
compute it to check a guess.

**Encryption at rest** — the disks are encrypted. Defends against physical
theft, and does nothing against someone who can run a query, because the
database decrypts transparently for them.

**Rate limiting** — capping how often something may be done, to blunt password
guessing, account enumeration, and quota exhaustion.

**Least privilege** — granting exactly the permissions needed and nothing more,
so that a compromise has a small blast radius.

**Allowlist and blocklist** — an allowlist permits only what is named; a
blocklist forbids only what is named. Allowlists fail safe, which is why both
the logging filter and the SSRF guard use one.

**Fail closed** — when something goes wrong, refuse rather than permit. The
application refuses to start rather than run with an unsafe setting.

---

## Data and privacy

**Personal data** — in this project: email, phone, first name, last name, date
of birth, IP address, payment details, and **any free text a user typed** —
including campaign titles, character names and every message. Explicitly *not*
personal here: username and display name.

**Plaintext** — readable data, before encryption or after decryption.
**Ciphertext** — the scrambled form.

**Pseudonymous** — identified by a value with no meaning outside the system.
Analytics uses a random identifier unrelated to the account.

**Anonymous** — genuinely unlinkable to a person. Analytics becomes anonymous
after the account is deleted and the link is destroyed.

**Threat model** — a written statement of who you are defending against and what
you are not defending against. A security claim without one is marketing.

**GDPR** — European data protection law. Relevant here mainly for its treatment
of IP addresses as personal data and its right to erasure.

---

## Databases

**Schema** — the structure: which tables exist, which columns, what types.

**Migration** — a numbered file of instructions that changes the schema. Applied
in order, once each, never edited after running anywhere real.

**Index** — a lookup structure making searches on a column fast. Also a second
copy of that column's contents, which is why indexing personal data would
quietly duplicate the thing you are protecting.

**Primary key** — the column uniquely identifying a row. **Foreign key** — a
column pointing at another table's primary key. The *absence* of a foreign key
between analytics and identity is deliberate and load-bearing here.

**Stored procedure** — SQL stored inside the database and called by name.

**ORM (Object Relational Mapper)** — a library turning database rows into
objects. Encryption in this project sits deliberately *above* it.

**Transaction** — a group of changes that all happen or none do.

---

## Artificial intelligence

**LLM (Large Language Model)** — the kind of program that generates the Dungeon
Master's narration. Gemini is one.

**Token** — the unit models count in, roughly three-quarters of a word. Quotas
and costs are measured in tokens.

**Prompt** — everything sent to the model: the standing instructions, the
conversation so far, and the newest message.

**System prompt** — the standing instruction shaping behaviour throughout. Ours
turns a general model into a Dungeon Master.

**Temperature** — how varied the output is. Higher suits storytelling; lower
suits extraction.

**Context window** — how much the model can consider at once. Ours sends the
last twenty messages, with the campaign premise restated each time.

**Finish reason** — why generation stopped. `STOP` is normal completion;
`SAFETY` means a filter fired; `max_tokens` means it was cut off.

**Free tier** — Google's no-cost usage allowance, with limits and — importantly
— terms permitting Google to use submitted content to improve their products.

---

## Infrastructure

**Container** — an application packaged with everything it needs to run, so it
behaves identically on any machine. Our backend ships as one; the frontend does
not need one, because it is just files.

**Dockerfile** — the recipe for building a container.

**Environment variable** — a setting supplied by whatever starts a program,
rather than written into it. Where secrets and per-environment addresses live.

**Secret** — a value that must not be committed: an API key, a password, an
encryption key.

**VPC (Virtual Private Cloud)** — your own private network inside AWS.

**Security group** — AWS's firewall, controlling which addresses may reach a
resource.

**Egress IP** — the address your outbound traffic appears to come from.
Distinct from the address people connect *to*, which catches many people out.

**OIDC (OpenID Connect)** — a way for one system to prove its identity to
another without a shared password. Lets Fly.io machines get short-lived AWS
credentials with no stored key.

**WAF (Web Application Firewall)** — a filter in front of your application that
blocks recognisably malicious requests. A bouncer checking people at the door
before they reach the room.

**CDN (Content Delivery Network)** — servers spread worldwide that cache your
files close to visitors.

**Reverse proxy** — a server sitting in front of another, forwarding requests.
Cloudflare and Fly.io both act as one here.

**Health check** — an address the platform polls to see whether your
application is alive. **Liveness** asks "is it running?"; **readiness** asks
"can it serve requests?". Confusing the two produces machines that restart
forever because their configuration is wrong.

**Rollback** — returning to the previous working version after a bad deploy.

---

## Game terms

**Dungeon Master (DM)** — the person, here a program, who describes the world,
plays every character in it, and adjudicates the rules.

**Campaign** — one ongoing story, played over many sessions.

**Session** — one sitting at the table.

**Character sheet** — the record of one adventurer: abilities, health,
equipment, history.

**Ability score** — a number from 1 to 30 describing a capability. 10 is
average. The **modifier**, added to dice rolls, is `(score − 10) ÷ 2` rounded
down.

**Ability check** — rolling a twenty-sided die and adding a modifier to see
whether an attempt succeeds.

**Hit points** — how much damage a character can take before falling.

**D&D 5e** — the fifth edition of Dungeons & Dragons, the ruleset used here.
