"""Tests for rate limiting, including the claim that it needs no plaintext."""

from __future__ import annotations

from app.config import RateLimitRule
from app.core.ratelimit import InMemoryRateLimiter


def test_requests_under_the_limit_are_allowed():
    """Normal use is not interfered with."""
    limiter = InMemoryRateLimiter()
    rule = RateLimitRule(limit=5, window_seconds=900)

    for _ in range(5):
        assert limiter.hit("198.51.100.7", "login", rule).allowed


def test_requests_over_the_limit_are_refused():
    """The sixth attempt in the window is stopped."""
    limiter = InMemoryRateLimiter()
    rule = RateLimitRule(limit=5, window_seconds=900)
    bucket = "198.51.100.7"

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

    limiter.hit("198.51.100.1", "login", rule)
    limiter.hit("198.51.100.1", "login", rule)
    assert limiter.hit("198.51.100.1", "login", rule).allowed is False
    assert limiter.hit("198.51.100.2", "login", rule).allowed is True


def test_scopes_are_counted_separately():
    """Using up your login attempts does not stop you playing the game."""
    limiter = InMemoryRateLimiter()
    rule = RateLimitRule(limit=1, window_seconds=60)
    bucket = "198.51.100.3"

    limiter.hit(bucket, "login", rule)
    assert limiter.hit(bucket, "login", rule).allowed is False
    assert limiter.hit(bucket, "chat", rule).allowed is True


def test_a_malformed_limit_is_rejected_at_startup():
    """A typo in configuration stops the application rather than disabling a limit."""
    import pytest

    with pytest.raises(ValueError, match="malformed"):
        RateLimitRule.parse("five-per-minute")
    with pytest.raises(ValueError, match="positive"):
        RateLimitRule.parse("0/60")
