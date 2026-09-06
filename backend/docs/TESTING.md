# Backend Testing

**Read this when** you are writing a test, or want to know what the existing 88
actually prove.

```bash
uv run pytest                          # all of them, about 2 seconds
uv run pytest tests/test_encryption.py # one file
uv run pytest -k redaction             # by name
uv run pytest --cov=app --cov-report=term-missing
```

---

## Two rules govern every test here

**1. No real personal data, ever.** Not in a fixture, not in an example, not in
a comment. Test data leaks — into bug reports, screenshots, and pasted terminal
output. Every address uses `example.com`, which IANA reserves for
documentation, and every name is invented.

Note that `example.invalid` looks like a safer choice and is not: it is a
reserved special-use domain, and the email validator rejects it, which produces
a confusing failure at runtime rather than at the point of the mistake.

**2. No real network calls.** A test that reached Google would be slow, flaky,
would spend the free quota, and would send test content to a third party. The
Gemini client is replaced by `FakeGemini`, which records what it was asked.

---

## What is faked, and what deliberately is not

| Component | Faked? | Why |
|---|---|---|
| Gemini | **Yes** | See rule 2 above |
| Encryption | **No** | It runs the real AES-256-GCM against the development key. A mock of encryption would prove nothing, and encryption is the part most worth testing |
| Blind index | **No** | Same reasoning |
| Password hashing | **No** | Real Argon2id. It makes the auth tests slower and they are still fast enough |
| Rate limiting | **No** | Real counters |
| Storage | In-memory | Which is what Phase 1 uses in production anyway |

**Encryption not being mocked is the single most important line in this table.**
The suite proves that ciphertext does not contain the plaintext, that a value
cannot be moved between users or columns, and that tampering is detected — none
of which a mock could tell you.

---

## Fixtures

Defined in `tests/conftest.py`.

| Fixture | Gives you |
|---|---|
| `settings` | Freshly loaded settings, cache cleared |
| `encryption` | A real `EncryptionService` on the development key |
| `blind_index` | A real `BlindIndexService` |
| `fake_gemini` | The stand-in AI, which records its calls |
| `client` | A `TestClient` for the whole application, AI faked, XSRF token already obtained |
| `xsrf` | The header needed for any state-changing request |

Environment variables are set at the top of `conftest.py`, before any
application module is imported, because settings are read at import time. That
keeps the suite reproducible on any machine regardless of the developer's
`.env`.

---

## What the suite proves

Grouped by what would break if someone got it wrong.

### `test_encryption.py` — the foundation

- Ciphertext does not contain the plaintext.
- The same text encrypts differently every time (which is why a blind index is
  needed at all).
- **A value encrypted for one column will not decrypt as another.**
- **A value encrypted for one user will not decrypt for another.**
- Flipping one bit causes a loud failure, not corrupted output.
- A shredded user's data cannot be decrypted, at all, ever.

The two bold ones are the additional-authenticated-data binding. They close an
attack where rows are shuffled rather than read.

### `test_blind_index.py` — searching without reading

- Determinism, and that capitalisation and whitespace do not create duplicates.
- The digest contains no trace of the address.
- **Without the key, the fingerprint cannot be recomputed** — the property that
  stops a stolen dump being tested against a guessed address.
- **IP fingerprints differ from one day to the next**, so counter rows cannot be
  assembled into a history.

### `test_redaction.py` — the most important file in the suite

Everything else protects data at rest. This protects it on the way past, into
log files that get shipped to third-party services and read by humans.

- Declared fields pass through; undeclared ones are censored.
- **A field invented after the code was written is censored by default.** This
  is the allowlist earning its keep.
- Censoring reveals shape but never content.
- **The filter fails closed** — if it raises, nothing gets through.
- **No personal field name has been added to the allowlist.** This test exists
  to fail if a future change widens the allowlist to make a log line more
  useful. That failure is the intended behaviour.

### `test_ssrf.py` — outbound safety

- The configured destination works; anything else is refused.
- Plain HTTP is refused.
- Every internal range is classified unsafe, including `169.254.169.254` — the
  cloud metadata address that hands out credentials.
- An unparseable address is treated as unsafe, because the safe answer to "I do
  not understand this" is no.

### `test_ratelimit.py` — abuse prevention without plaintext

- Limits allow and then refuse; callers and scopes are counted separately.
- **The whole path runs on a 32-byte digest.** This is the test backing the
  claim that privacy and security do not trade off here.
- A malformed limit in configuration stops startup rather than silently
  disabling a limit.

### `test_scrubber.py` — what leaves for Google

- Emails, phone numbers, card numbers, postcodes, links and dates are removed.
- **Ordinary play is left completely alone**, and character names survive. A
  privacy control that ruins the product gets switched off, and a control that
  is switched off protects nobody.

### `test_api_security.py` — the HTTP layer

- State-changing requests need the XSRF token; reads do not.
- Security headers are present; HSTS is not sent locally.
- Correlation identifiers are unique per request, and a hostile supplied value
  is not trusted.
- **Login failures are byte-for-byte indistinguishable** whether or not the
  account exists.
- **Validation errors never echo the submitted value.**
- One user cannot read another's campaign, and gets 404 rather than 403.

### `test_chat.py` — the game loop

- A turn returns narration and stores both messages.
- **The stored transcript is ciphertext** — this test reaches into the store and
  asserts the words are not in the bytes.
- **Personal data is scrubbed before reaching the model**, but the player's own
  words are kept unscrubbed for them. It is their campaign.
- Over-long, empty, and unknown-field requests are rejected.

### `test_deletion_and_analytics.py` — deletion and the allowlist

- **Crypto-shredding leaves the ciphertext in place and destroys the key**, and
  the account then cannot be used or found.
- Deletion requires exact confirmation.
- Analytics rejects undeclared events, features and categories.
- The analytics identifier is unrelated to the account identifier.
- **Severing the link keeps the counts and orphans the events.**

---

## Writing a new test

Name it as a sentence describing behaviour:

```python
def test_ciphertext_cannot_be_moved_to_another_user(encryption): ...
def test_login_failures_are_indistinguishable(client, xsrf): ...
```

When a test exists to prevent a specific mistake, say so in the docstring — the
next person needs to know what breaks if they "fix" it.

For an endpoint test, use the `client` and `xsrf` fixtures:

```python
def test_something(client, xsrf):
    response = client.post("/api/v1/campaigns", json={"title": "Test"}, headers=xsrf)
    assert response.status_code == 201
```

**A trap worth knowing.** Asserting that a value is absent from a response is
easy to get wrong: a test using the password `"short"` failed because `short`
appears inside the error type `string_too_short`. Choose distinctive test values
when asserting absence.

---

## Coverage

No enforced percentage, because a percentage measures lines executed rather
than behaviour verified. What is expected instead:

- **Every security control has a test that would fail if it were removed.**
- **Every privacy claim in the documentation has a test behind it.** If a
  document says data cannot be moved between users, a test proves it.
- Every endpoint has at least a success and a failure case.
- Every error path a user can reach returns the right code and no personal data.

If you cannot write a test that fails when a control is removed, the control is
probably not doing what the comment says.

---

## Synthetic seed data

```bash
uv run uvicorn app.main:app --reload --port 8000   # terminal 1
uv run python scripts/seed_dev_data.py             # terminal 2
```

Creates three accounts with campaigns and characters, using Faker with a fixed
seed so the same invented people appear every run — which makes debugging
repeatable.

**Never copy production data to a laptop.** It would defeat every control at
once: a developer machine has no KMS key policy, no audit log, no redacted
logging, and is backed up to somebody's personal cloud storage. One copy and
the boundary is gone.

The script goes through the real API rather than writing to the store directly,
so seeded data passes through the same validation and encryption as real data.
If the seed script works, the real path works.

---

## Local versus production security posture

| | Local | Production |
|---|---|---|
| Encryption key | Fixed, in `.env`, published | AWS KMS hardware |
| Can you read the data? | Yes, deliberately | No, not even as administrator |
| Authentication | Stubbed | Signed tokens |
| Storage | Memory | MySQL with TLS |
| Logs | Console, redaction on | JSON, redaction enforced |

Local is deliberately inspectable so you can see what is happening. The
application prints a large `DEVELOPMENT MODE — NOT SECURE` banner at startup
and **refuses to start** in these modes when `APP_ENV=production`.

**Never point local configuration at production data.** There is no safe
version of that, and the fail-closed checks exist because good intentions are
not a control.

---

## Related documents

- [SECURITY.md](SECURITY.md) — what the security tests are testing.
- [OBSERVABILITY.md](OBSERVABILITY.md) — the redaction allowlist.
- [CONVENTIONS.md](CONVENTIONS.md) — house style.
