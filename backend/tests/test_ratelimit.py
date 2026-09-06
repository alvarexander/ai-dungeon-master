"""Tests for rate limiting, including the claim that it needs no plaintext."""

from __future__ import annotations

from app.config import RateLimitRule
from app.core.ratelimit import InMemoryRateLimiter


def test_requests_under_the_limit_are_allowed():
    """Normal use is not interfered with."""
    limiter = InMemoryRateLimiter()
    rule = RateLimitRule(limit=5, window_seconds=900)

    for _ in range(5):
        assert limiter.hit(b"bucket" + b"\0" * 26, "login", rule).allowed


def test_requests_over_the_limit_are_refused():
    """The sixth attempt in the window is stopped."""
    limiter = InMemoryRateLimiter()
    rule = RateLimitRule(limit=5, window_seconds=900)
    bucket = b"bucket" + b"\0" * 26

    for _ in range(5):
        limiter.hit(bucket, "login", rule)

    result = limiter.hit(bucket, "login", rule)
    assert result.allowed is False
    assert result.hit_count == 6
    assert result.retry_after_seconds > 0


def test_different_callers_have_separate_allowances():
    """One person hitting their limit does not lock out everybody else."""
    limiter = InMemoryRateLimiter()
    rule = RateLimitRule(limit=2, window_seconds=60)

    limiter.hit(b"a" * 32, "login", rule)
    limiter.hit(b"a" * 32, "login", rule)
    assert limiter.hit(b"a" * 32, "login", rule).allowed is False
    assert limiter.hit(b"b" * 32, "login", rule).allowed is True


def test_scopes_are_counted_separately():
    """Using up your login attempts does not stop you playing the game."""
    limiter = InMemoryRateLimiter()
    rule = RateLimitRule(limit=1, window_seconds=60)
    bucket = b"c" * 32

    limiter.hit(bucket, "login", rule)
    assert limiter.hit(bucket, "login", rule).allowed is False
    assert limiter.hit(bucket, "chat", rule).allowed is True


def test_the_whole_path_runs_on_a_digest(blind_index):
    """The demonstration that abuse prevention needs no readable identifier.

    An address goes in one end as text, is immediately fingerprinted, and from
    that point on the rate limiter only ever sees 32 opaque bytes. Nothing in
    the counter store can be turned back into an address.
    """
    limiter = InMemoryRateLimiter()
    rule = RateLimitRule(limit=3, window_seconds=60)

    bucket = blind_index.ip_digest("203.0.113.42")
    assert isinstance(bucket, bytes)
    assert len(bucket) == 32
    assert b"203" not in bucket

    for _ in range(3):
        assert limiter.hit(bucket, "chat", rule).allowed
    assert limiter.hit(bucket, "chat", rule).allowed is False


def test_a_malformed_limit_is_rejected_at_startup():
    """A typo in configuration stops the application rather than disabling a limit."""
    import pytest

    with pytest.raises(ValueError, match="malformed"):
        RateLimitRule.parse("five-per-minute")
    with pytest.raises(ValueError, match="positive"):
        RateLimitRule.parse("0/60")
