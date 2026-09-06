"""Tests for the log redaction allowlist.

The most important tests in the suite. Everything else protects data at rest;
this protects it on the way past. A leak here would put plaintext into log
files that are shipped to third-party services and read by humans.
"""

from __future__ import annotations

from app.core.logging import LOGGABLE_FIELDS, describe, redaction_processor


def test_declared_fields_pass_through():
    """Fields on the allowlist are written as they are."""
    result = redaction_processor(None, "info", {"event": "login_succeeded", "status_code": 200})
    assert result["event"] == "login_succeeded"
    assert result["status_code"] == 200


def test_undeclared_fields_are_replaced():
    """A field nobody declared is censored, by default, without being asked."""
    result = redaction_processor(None, "info", {"event": "x", "email": "player@example.com"})
    assert result["email"] == "<str:len=18>"
    assert "player" not in str(result)


def test_a_brand_new_field_is_censored():
    """The point of an allowlist: tomorrow's field is protected today.

    A denylist protects only against the leaks somebody already thought of.
    This test is the difference — a field invented after this code was written
    is censored without anyone having to remember to add it.
    """
    result = redaction_processor(
        None, "info", {"event": "x", "recovery_phone_number": "+44 7700 900123"}
    )
    assert "7700" not in str(result)
    assert result["recovery_phone_number"].startswith("<str:len=")


def test_censoring_reveals_shape_but_not_content():
    """A censored value still helps debugging without disclosing anything."""
    assert describe("player@example.com") == "<str:len=18>"
    assert describe("") == "<str:len=0>"
    assert describe(None) == "<none>"
    assert describe({"a": 1, "b": 2}) == "<dict:keys=2>"
    assert describe([1, 2, 3]) == "<list:len=3>"
    assert describe(b"\x00\x01") == "<bytes:len=2>"


def test_numbers_are_censored_by_type_not_value():
    """An undeclared number could be a date of birth, so its value is hidden."""
    assert describe(1987) == "<int>"
    assert describe(1.5) == "<float>"


def test_the_filter_fails_closed():
    """If redaction itself breaks, nothing gets through.

    A redaction filter that failed open would be worse than having none,
    because it would create confidence that is not warranted.
    """

    class Explosive:
        def __len__(self) -> int:
            raise RuntimeError("boom")

        def __repr__(self) -> str:
            raise RuntimeError("boom")

    class ExplosiveDict(dict):
        def items(self):
            raise RuntimeError("boom")

    result = redaction_processor(None, "error", ExplosiveDict(secret="player@example.com"))
    assert result["event"] == "log_redaction_failed"
    assert "player" not in str(result)


def test_no_personal_field_names_are_on_the_allowlist():
    """A guard against someone widening the allowlist to silence a warning.

    If a future change adds ``email`` to the allowlist to make a log line more
    useful, this test fails and says why. That is the intended behaviour.
    """
    forbidden = {
        "email", "phone", "first_name", "last_name", "password", "date_of_birth",
        "ip", "ip_address", "client_ip", "transcript", "prompt", "response",
        "content", "message", "backstory", "title", "premise", "name",
    }
    overlap = forbidden & LOGGABLE_FIELDS
    assert not overlap, (
        f"These personal-data field names have been added to the log allowlist: {overlap}. "
        "Log an opaque identifier instead, or a length, or a category."
    )
