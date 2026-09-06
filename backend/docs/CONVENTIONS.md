# Backend Conventions

**Read this when** you are about to write backend code and want to match what
is already there. It covers module layout, Pydantic models, error handling,
docstrings, async usage, and the dependency rules between layers.

---

## The dependency rule

**Routes → services → repositories. Never backwards, never skipping.**

| Layer | May import from | May never import |
|---|---|---|
| `api/` | `services`, `schemas`, `core` | another route |
| `services/` | `repositories`, `core`, `schemas` | anything in `api/` |
| `repositories/` | `core` | anything in `services/` or `api/` |
| `core/` | nothing above it | everything above it |

If a service needs something from a route, the design is wrong: pass it as an
argument instead.

---

## Docstrings

**Every function gets one**, written for a reader who has never programmed.
Google style, enforced by `ruff` rule `D`.

The standard is higher than "document the parameters". A docstring on a
function that encrypts should explain what encryption is doing *in that
context* and why it matters — not restate the signature.

```python
def crypto_shred(self, user_id: UUID) -> datetime:
    """Delete an account by destroying its encryption key.

    Look at what this method does not do. It never touches the campaigns,
    the characters, or the transcripts. It removes one small field — the
    wrapped key — and at that instant every encrypted byte belonging to
    this account becomes permanently undecryptable, here and in any backup
    that was ever taken.

    Args:
        user_id: Which account.

    Returns:
        When the key was destroyed.

    Raises:
        KeyError: If the account does not exist.
    """
```

Include `Raises:` whenever the caller could reasonably be surprised.

---

## Naming

| Thing | Style | Example |
|---|---|---|
| Modules | lower_snake | `blind_index.py` |
| Classes | PascalCase | `EncryptionService` |
| Functions | lower_snake | `verify_password` |
| Constants | UPPER_SNAKE | `KEY_CACHE_TTL_SECONDS` |
| Private | leading underscore | `_daily_salt` |

No special suffixes are needed: columns are named for what they hold.

---

## Pydantic models

Every request and response has one. They live in `app/schemas/`.

**Inherit from `ApiModel`**, which forbids unknown fields — so a typo like
`mesage` becomes an immediate error rather than a silently ignored field.

**Describe and give an example for every field.** These become the Swagger
documentation, which is the first thing anyone reads:

```python
message: str = Field(
    min_length=1,
    max_length=4000,
    description=(
        "What the player says or does. Treated as personal data throughout: "
        "players type real names into free text, so it is encrypted at rest "
        "and scrubbed before being sent to Google."
    ),
    examples=["I push open the chapel door and hold up the lantern."],
)
```

**Every example is invented.** No real address, no real name. Use
`example.com`, which IANA reserves for documentation. Swagger examples are
published to anyone who can reach `/docs`.

**Constrain aggressively.** A `max_length` is input validation, and sometimes
more: the 200-character cap on passwords exists so that an enormous submission
cannot be used to make the server do expensive hashing — a denial of service
through the password field.

---

## Errors

Raise a subclass of `ApiError`. Never let an exception reach the browser
unshaped.

```python
raise NotFoundError("campaign")
raise RateLimitedError(retry_after_seconds=42, scope="chat")
```

Four rules:

1. **Every error carries the correlation identifier.** Added automatically by
   the handler. It is what replaces "let me look at your account".
2. **Never put personal data in a message.** The field name, yes; its contents,
   never. Error messages reach logs.
3. **Authentication errors are uniform.** Identical whether the account does
   not exist, the password is wrong, or the account is suspended. Anything more
   specific is a map of who is registered.
4. **Not-found beats forbidden.** Returning 403 for someone else's resource
   confirms the identifier is real. Return 404 for both.

---

## Async

Route handlers and service methods are `async`. The reason is concrete: a
Gemini call takes several seconds, and async lets one worker serve other
players during the wait instead of being tied up.

**Never make a blocking call inside async code.** A blocking call freezes the
entire server — every other player's request stops until it returns. The two
that matter here:

```python
# Wrong: freezes the server for the length of the lookup.
infos = socket.getaddrinfo(host, None)

# Right: runs on a worker thread.
loop = asyncio.get_running_loop()
infos = await loop.getaddrinfo(host, None)
```

```python
# Wrong: loading a speech model takes tens of seconds.
model = WhisperModel(size)

# Right.
model = await asyncio.to_thread(WhisperModel, size)
```

This is not theoretical — it was found in this codebase during Phase 1 by
noticing that a failing request took fifteen seconds longer than its own
timeout.

---

## Logging

```python
_log = get_logger("gemini")

# Right: a fixed event name, variables in named fields.
_log.info("gemini_call_completed", model_id=model, latency_ms=elapsed)

# Wrong: the address goes straight into the log, past the filter.
_log.info(f"login failed for {email}")
```

**Event names are fixed strings, never f-strings.** The redaction filter
inspects fields; it cannot inspect a message somebody has already interpolated.
This is the one hole the allowlist cannot close, so it is a convention enforced
by review.

The rule to follow: **log identifiers, not contents.** A `user_id` tells you
which account without putting anybody's words in a file that gets copied to log
aggregators and read by people.

---

## Configuration

Every setting goes in `Settings` with a matching entry in `.env.example`
explaining it in plain language.

**No `localhost` defaults.** A missing value must stop startup. A default that
silently works on a laptop is a default that silently breaks in production.

**Anything unsafe in production goes in `validate_production_safety`**, which
refuses to start rather than trusting whoever deploys to remember.

---

## Tests

Named as sentences describing behaviour:

```python
def test_ciphertext_cannot_be_moved_to_another_user(encryption): ...
def test_login_failures_are_indistinguishable(client, xsrf): ...
```

When a test exists to prevent a specific mistake, say so in its docstring. See
[TESTING.md](TESTING.md).

---

## Commits

Plain and descriptive. Subject line alone by default; a body only when the
change is not self-explanatory, and then one paragraph with no bullet lists.

**No AI attribution** — no `Co-Authored-By`, no "generated with", no footers.

Schema, encryption or telemetry changes update their document **in the same
commit**.
