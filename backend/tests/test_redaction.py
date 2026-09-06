"""Tests that credentials never reach the log.

A log file is copied, shipped to other services, and read by people. Passwords
and tokens must not be in it, even briefly, and these tests fail if that ever
stops being true.
"""

from __future__ import annotations

import pytest

from app.core.logging import REDACTED, is_sensitive, redaction_processor


@pytest.mark.parametrize(
    "field_name",
    [
        "password",
        "Password",
        "new_password",
        "password_hash",
        "api_key",
        "GEMINI_API_KEY",
        "apikey",
        "access_token",
        "refresh_token",
        "authorization",
        "cookie",
        "client_secret",
        "private_key",
        "db_credential",
    ],
)
def test_credential_shaped_names_are_recognised(field_name):
    """Every common spelling of a secret is caught, including odd casings."""
    assert is_sensitive(field_name) is True


@pytest.mark.parametrize(
    "field_name",
    ["user_id", "status_code", "duration_ms", "event", "model_id", "tokens_in", "path"],
)
def test_ordinary_field_names_are_left_alone(field_name):
    """Normal operational fields are not touched, or logs become useless."""
    assert is_sensitive(field_name) is False


def test_ai_token_counts_are_not_mistaken_for_credentials():
    """`tokens_in` must survive, even though it contains the word "token".

    A naive substring check redacts it, which silently destroys the numbers the
    whole cost and performance story depends on — and looks like the filter
    working correctly. Matching is on whole words for exactly this reason.
    """
    result = redaction_processor(
        None, "info", {"event": "gemini_call_completed", "tokens_in": 820, "tokens_out": 240}
    )

    assert result["tokens_in"] == 820
    assert result["tokens_out"] == 240


def test_a_secret_value_is_replaced():
    """The value goes; the field name stays, so you can still see it was there."""
    result = redaction_processor(
        None, "info", {"event": "login_attempt", "password": "correct-horse-battery"}
    )

    assert result["password"] == REDACTED
    assert "correct-horse-battery" not in str(result)
    assert result["event"] == "login_attempt"


def test_several_secrets_are_all_replaced():
    """One sensitive field in an entry does not mask another being missed."""
    result = redaction_processor(
        None,
        "info",
        {"event": "x", "api_key": "AIzaSy-something", "access_token": "abc123", "user_id": "u1"},
    )

    assert result["api_key"] == REDACTED
    assert result["access_token"] == REDACTED
    assert result["user_id"] == "u1"


def test_the_filter_fails_closed():
    """If redaction itself breaks, nothing gets through.

    A filter that failed open would be worse than having none at all, because
    it would create confidence that is not warranted.
    """

    class ExplosiveDict(dict):
        def items(self):
            raise RuntimeError("boom")

    exploding = ExplosiveDict(password="hunter2")  # noqa: S106 - deliberately fake
    result = redaction_processor(None, "error", exploding)

    assert result["event"] == "log_redaction_failed"
    assert "hunter2" not in str(result)


def test_no_endpoint_logs_a_request_body():
    """The request body is never logged, only the shape of the request.

    Read as a guard rather than a unit test: it checks the middleware records
    the method, path, status and duration, and nothing from the body. If
    somebody adds body logging, this is where it should be noticed.
    """
    import inspect

    from app.middleware.correlation import CorrelationMiddleware

    source = inspect.getsource(CorrelationMiddleware)

    assert "request_completed" in source
    assert "await request.body()" not in source
    assert "request.json()" not in source
