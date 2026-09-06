"""Shared test fixtures.

WHY THE TESTS DO NOT USE REAL ENCRYPTION KEYS OR A REAL AI
Two rules govern every test in this suite:

1. **No real personal data, ever.** Not in a fixture, not in an example, not in
   a comment. Test data leaks — into bug reports, screenshots and pasted
   output — so every value here is invented and every email address uses
   `example.com`, which IANA reserves for documentation.
2. **No real network calls.** Tests that reached Google would be slow,
   flaky, would consume the free quota, and would send test content to a third
   party. The Gemini client is replaced with a fake.

Password hashing is **not** faked. Tests run real Argon2id, which makes the
authentication tests a little slower and means they actually verify the thing
that matters.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import pytest

# Configuration must be in place before any application module is imported,
# because settings are read at import time. Setting them here rather than
# relying on a .env file keeps the suite reproducible on any machine.
_TEST_ENV = {
    "APP_ENV": "local",
    "CORS_ALLOWED_ORIGINS": "http://localhost:4200",
    "GEMINI_API_KEY": "test-key-not-real",
    "GEMINI_BASE_URL": "https://generativelanguage.googleapis.com",
    "LOG_FORMAT": "console",
    "LOG_LEVEL": "WARNING",
    "AUTH_MODE": "stub",
    "REPOSITORY_BACKEND": "memory",
    "STT_ENABLED": "false",
}
for _key, _value in _TEST_ENV.items():
    os.environ.setdefault(_key, _value)


@pytest.fixture
def settings() -> Any:
    """Return freshly loaded application settings.

    Returns:
        The settings object, with the cache cleared first so that a test which
        changed an environment variable sees its change.
    """
    from app.config import get_settings

    get_settings.cache_clear()
    return get_settings()


class FakeGemini:
    """Stands in for the Gemini client so tests never touch the network.

    Records what it was asked, which lets a test assert that the outbound
    prompt was scrubbed — without ever sending anything anywhere.
    """

    def __init__(self, reply: str = "The door gives with a groan of swollen wood.") -> None:
        """Set up the fake.

        Args:
            reply: What to return as the Dungeon Master's narration.
        """
        self.reply = reply
        self.calls: list[dict[str, Any]] = []

    async def generate(self, **kwargs: Any) -> Any:
        """Pretend to call the model and return a fixed reply.

        Args:
            **kwargs: The same arguments the real client takes. Recorded so
                tests can inspect exactly what would have been sent.

        Returns:
            A ``GeminiResult`` with plausible metrics.
        """
        from app.services.gemini import GeminiResult

        self.calls.append(kwargs)
        return GeminiResult(
            text=self.reply,
            tokens_in=120,
            tokens_out=45,
            finish_reason="STOP",
            latency_ms=1200,
            model_id="gemini-3.5-flash",
            retry_count=0,
        )

    async def aclose(self) -> None:
        """Match the real client's interface. Does nothing."""


@pytest.fixture
def fake_gemini() -> FakeGemini:
    """Return a fake Gemini client.

    Returns:
        The fake, which records the calls made to it.
    """
    return FakeGemini()


@pytest.fixture
def client(fake_gemini: FakeGemini) -> Iterator[Any]:
    """Return a test client for the full application, with the AI faked.

    Args:
        fake_gemini: The stand-in AI client.

    Yields:
        A ``TestClient`` with a cross-site request forgery token already
        obtained, so tests do not have to repeat that dance.
    """
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        # Swap the real AI client for the fake, after startup has built the
        # container. Replacing one attribute is enough because the game service
        # holds a reference to the same object.
        app.state.container.gemini = fake_gemini
        app.state.container.game._gemini = fake_gemini  # noqa: SLF001
        test_client.get("/health")  # obtains the XSRF cookie
        yield test_client


@pytest.fixture
def xsrf(client: Any) -> dict[str, str]:
    """Return the header needed for any state-changing request.

    Args:
        client: The test client, which already holds the cookie.

    Returns:
        A headers dictionary carrying the token.
    """
    return {"X-XSRF-TOKEN": client.cookies.get("XSRF-TOKEN", "")}
