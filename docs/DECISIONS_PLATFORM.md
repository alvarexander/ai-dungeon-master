# Architecture Decisions — Platform

**Read this when** you want to know why the backend framework, the hosting
split, the code layering, or the cross-cloud connections are the way they are.
For decisions about encryption, privacy and telemetry, read
[Architecture Decisions — Privacy](DECISIONS_PRIVACY.md) instead. The index of
all decisions is in [ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md).

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

## ADR-001 — Python web framework: FastAPI

**The question.** The backend (the program that runs on a server, talks to the
database and the AI, and answers requests from the browser) needs a *web
framework* — a library that handles the plumbing of receiving a request over the
network and sending a reply.

**The decision.** FastAPI.

**Why.** Three reasons, in order of importance.

1. **Swagger comes free.** *Swagger*, also called *OpenAPI*, is a
   machine-readable description of every URL your backend answers: what it
   accepts, what it returns, what can go wrong. From that description, a
   browsable documentation page is generated automatically. You asked for this
   without bolting on a second library. FastAPI generates it from the code
   itself — the same type declarations that validate incoming data also produce
   the documentation, so the two can never drift apart. Visit `/docs` and it is
   simply there.

2. **It is asynchronous by nature.** When the backend asks Google Gemini for a
   Dungeon Master reply, it waits — often two to six seconds. A traditional
   framework ties up one worker for that whole wait, so ten simultaneous players
   need ten workers. *Asynchronous* code lets a single worker start a request,
   put it aside while the network does its slow thing, and serve other players
   in the meantime. For an application whose main job is waiting on a slow AI,
   this is the difference between one small server and several large ones.

3. **Dependency injection is built in.** *Dependency injection* is a pattern
   where a function declares what it needs — "give me the current user", "give
   me a database session" — and the framework supplies it. This keeps
   security checks (rate limiting, token validation) out of the body of every
   endpoint and in one declared place, which means they cannot be forgotten.

**What was rejected.**

- **Django REST Framework.** Excellent for database-heavy applications with an
  admin interface. But OpenAPI requires the extra `drf-spectacular` package —
  exactly the bolt-on you ruled out — and Django's asynchronous support is still
  partial. Django's biggest selling point, the automatic admin interface, is
  actively *useless* here: an admin panel that displays user records is a
  plaintext-viewing tool, and this design forbids that (see ADR-004).
- **Flask.** Small and pleasant, but every feature you need is a separate
  package: `flask-smorest` for OpenAPI, an extension for validation, another for
  async. Three bolt-ons instead of one.

**Cost to reverse.** Expensive. The whole backend is written against FastAPI's
idioms.

---

---

## ADR-009 — Server-Side Rendering stays off

**The question.** Angular can run in two modes: build to plain files that any
web server can hand out, or run a Node.js program that assembles each page on
the server before sending it.

**The decision.** Plain files. No SSR, no Angular Universal.

**Why.** Hostinger's static hosting serves files. It does not run a Node.js
process for you. Enabling SSR would make the frontend undeployable to the tier
you have chosen. This is not a preference; it is a hard constraint flowing from
the hosting decision.

**What you give up.** Two things, both currently irrelevant. Search engines see
an empty page until JavaScript runs, which does not matter for an application
behind a login. And the first page load is slightly slower, because the browser
must download the code before it can draw anything.

**What would need to change if you ever turn it on.** Documented in the frontend
repository's [architecture notes](../frontend/docs/ARCHITECTURE.md) — chiefly
that the hosting tier must move off Hostinger to somewhere that runs Node, and
that every piece of code touching `window`, `document`, or `localStorage` needs
a guard, because none of those exist on a server.

**Cost to reverse.** Moderate, and it drags the hosting decision with it.

---

---

## ADR-010 — Layering: routes → services → repositories

**The question.** How is the backend code organised so that encryption cannot be
accidentally skipped?

**The decision.** Three layers with a strict one-way dependency rule.

- **Routes** speak HTTP. They validate the incoming shape, and nothing else.
- **Services** hold the rules of the game and of the business. They work with
  ordinary Python objects containing plaintext.
- **Repositories** are the only code permitted to touch the database. They
  encrypt on the way in and decrypt on the way out.

A route may call a service. A service may call a repository. Nothing calls
backwards. The rule matters because it puts encryption at a **choke point**: it
is impossible to save a user's email without passing through the one repository
that knows to encrypt it. Correctness stops depending on whether whoever wrote
the newest endpoint remembered.

**Cost to reverse.** Moderate.

---

---

## ADR-011 — Cross-cloud database access: public endpoint, locked to one address

**The question.** The backend runs on Fly.io. The database runs on AWS. They are
in different companies' networks, so the database cannot simply be marked
"private" and remain reachable. This is the hardest problem in the deployment.

**The decision.** Make the database publicly *routable* but reachable only from
a single fixed address — a **static egress IP** rented from Fly.io for
$3.60/month — enforced by an AWS security group. TLS is mandatory on the
connection.

**Why, when "publicly accessible" sounds so wrong.** Two reasons.

First, the phrase oversells the risk. A *security group* is AWS's firewall. Set
to allow exactly one address and one port, the database refuses to answer
anyone else — it does not respond to a scan, it does not offer a login prompt,
it is not "on the internet" in any way an attacker can use. It is a locked door
in an alley only one person knows the address of.

Second, and more importantly: **your security does not rest on this**. The
threat model already assumes the attacker has the whole database. That is why
everything in it is ciphertext. Network isolation is a useful additional wall,
not the wall.

The alternative approaches — a WireGuard tunnel, Tailscale, an AWS bastion host
— each add a second always-on machine that can break at 3am and that you would
have to debug. For one backend, one developer, and low traffic, that complexity
buys less than it costs. The full comparison, with the reasoning for when you
*should* upgrade, is in
[the cross-cloud deployment guide](DEPLOY_CROSS_CLOUD.md).

**Cost to reverse.** Cheap. Moving to Tailscale later changes a connection
string and a firewall rule.

**A cheaper option that avoids the problem entirely.** Putting the database on
Hostinger — where you are already paying for hosting — means there is no AWS
network to reach into, and this decision does not apply. See
[DEPLOY_MYSQL_HOSTINGER.md](DEPLOY_MYSQL_HOSTINGER.md).

---

---

## ADR-013 — Two storage backends behind one interface

**The question.** You want to run this immediately, without installing a
database first — but you also want data that survives a restart.

**The decision.** Two implementations of the same repository interfaces. An
in-memory store is the default; MySQL is one environment variable away.

```
REPOSITORY_BACKEND=memory   # nothing to install, lost on restart  (default)
REPOSITORY_BACKEND=mysql    # real database, survives restarts
```

**Why both rather than picking one.** Requiring MySQL before anything runs puts
a database installation between a newcomer and their first working page, which
is exactly the point at which people give up. Shipping only the in-memory store
would mean the real storage path was untested until deployment day.

Both satisfy the interfaces in `repositories/base.py`, so nothing above that
layer knows which one it got. `docs/LOCAL_MYSQL.md` walks through installing
MySQL locally.

**What is genuinely different between them.** Only where the bytes land. The
same ownership checks, the same sequence-number locking, the same cascade
behaviour on deletion.

**Cost to reverse.** Cheap — that is the point of the interface.

---

## ADR-014 — Plain SQL, not an ORM

**The question.** How does the MySQL implementation talk to the database?

**The decision.** Hand-written SQL with named parameters, through SQLAlchemy's
connection handling but not its object mapper.

**Why.** An ORM (Object Relational Mapper) turns rows into objects
automatically. It saves typing on large projects and hides what is actually
happening — which is the wrong trade when someone is learning. Every query in
`repositories/sql.py` can be read, copied into a database client, and run. When
something is slow or wrong, the thing to look at is right there.

It also removes a category of surprise: no lazy loading, no session-flush
ordering, no wondering which attribute access triggered a query.

**What was rejected.** SQLAlchemy's ORM, and stored procedures. Stored
procedures were in an earlier version and were removed — they put the logic in
a second place, they are awkward to review in a pull request, and some shared
hosting plans do not permit creating them at all.

**The one rule that is not negotiable.** Every query uses named parameters —
`:user_id`, never an f-string. That is what makes SQL injection impossible, and
it is the most common serious web vulnerability.

**Cost to reverse.** Moderate.
