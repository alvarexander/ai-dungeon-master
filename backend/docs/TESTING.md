# Backend Testing

**Read this when** you are writing a test, or want to know what the existing 88
actually prove.

```bash
uv run pytest                          # all 90, about 2 seconds
uv run pytest tests/test_redaction.py  # one file
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
| Password hashing | **No** | Real Argon2id. It makes the authentication tests slower and means they verify the thing that matters |
| Rate limiting | **No** | Real counters |
| Storage | In-memory | Which is what the default configuration uses anyway |

**Password hashing not being mocked is the important row.** It is the one
control protecting something that cannot be re-issued if it leaks, so the tests
exercise the real thing.

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

Grouped by what would break if somebody got it wrong.

### `test_redaction.py` — credentials stay out of logs

- Every common spelling of a secret is caught: `password`, `api_key`,
  `access_token`, `authorization`, `client_secret`, and odd casings of each.
- **`tokens_in` is not mistaken for a credential.** A naive substring check on
  `token` redacts the AI token counts, silently destroying the numbers the
  whole cost story depends on — and it looks like the filter working. That is a
  real bug this test caught.
- The filter **fails closed**: if it raises, nothing gets through.
- No endpoint logs a request body.

### `test_ssrf.py` — outbound safety

- The configured destination works; anything else is refused.
- Plain HTTP is refused.
- Every internal range is classified unsafe, including `169.254.169.254` — the
  cloud metadata address that hands out credentials.
- An unparseable address is treated as unsafe, because the safe answer to "I do
  not understand this" is no.

### `test_ratelimit.py` — abuse prevention

- Limits allow and then refuse; callers and scopes are counted separately.
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
- **Personal data is scrubbed before reaching the model**, but the player's own
  words are stored unchanged for them. It is their campaign.
- Over-long, empty, and unknown-field requests are rejected.
- A session belonging to somebody else is not readable.

### `test_deletion_and_analytics.py` — deletion and the analytics allowlist

- **Deleting an account removes everything it owned**, and the account then
  cannot be used or found.
- Deletion requires exact confirmation.
- Analytics rejects undeclared events, features and categories.
- **Deleting a user clears their events but keeps the totals correct.**

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

**Never copy production data to a laptop.** A developer machine has no
firewall in front of it, no access logging, and is backed up to somebody's
personal cloud storage. One copy and every control you put in place is gone.

The script goes through the real API rather than writing to the store directly,
so seeded data passes through the same validation and encryption as real data.
If the seed script works, the real path works.

---

## Local versus production

| | Local | Production |
|---|---|---|
| Storage | Memory, or a local MySQL | MySQL behind a firewall |
| Database reachable from | Your machine only | The backend's address only |
| Authentication | Stubbed | Signed tokens (Phase 2) |
| Connection | Plain, on localhost | TLS, enforced by the server |
| Logs | Console | JSON, shipped somewhere |

The application prints a `DEVELOPMENT MODE — NOT SECURE` banner at startup and
**refuses to start** with stubbed authentication when `APP_ENV=production`.

**Never point local configuration at production data.** There is no safe
version of that, and the fail-closed checks exist because good intentions are
not a control.

---

## Related documents

- [SECURITY.md](SECURITY.md) — what the security tests are testing.
- [OBSERVABILITY.md](OBSERVABILITY.md) — the redaction allowlist.
- [CONVENTIONS.md](CONVENTIONS.md) — house style.
