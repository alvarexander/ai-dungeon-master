"""Tests for keyed fingerprints: email lookup and privacy-preserving IP counting."""

from __future__ import annotations

from datetime import UTC, datetime


def test_the_same_email_always_produces_the_same_fingerprint(blind_index):
    """Determinism is what makes the fingerprint searchable."""
    assert blind_index.email_index("player@example.com") == blind_index.email_index(
        "player@example.com"
    )


def test_capitalisation_and_whitespace_do_not_matter(blind_index):
    """Normalisation stops one person accidentally creating two accounts."""
    canonical = blind_index.email_index("player@example.com")
    assert blind_index.email_index("Player@Example.COM") == canonical
    assert blind_index.email_index("  player@example.com  ") == canonical


def test_different_emails_produce_unrelated_fingerprints(blind_index):
    """Two addresses that differ by one character share nothing recognisable."""
    first = blind_index.email_index("player@example.com")
    second = blind_index.email_index("qlayer@example.com")
    assert first != second
    # Fewer than half the bytes should coincide by chance.
    matching = sum(1 for a, b in zip(first, second, strict=True) if a == b)
    assert matching < 16


def test_the_fingerprint_does_not_contain_the_address(blind_index):
    """The digest is 32 opaque bytes with no trace of the input."""
    digest = blind_index.email_index("player@example.com")
    assert len(digest) == 32
    assert b"player" not in digest


def test_the_fingerprint_depends_on_the_secret_key(blind_index, settings):
    """Without the key, the fingerprint cannot be recomputed.

    This is the property that stops an attacker with a database dump testing
    whether a given address is registered. Change the key and every fingerprint
    changes, so a dump alone tells them nothing.
    """
    from app.core.security.blind_index import BlindIndexService

    other = BlindIndexService(index_key=b"a-completely-different-key-32byte", ip_secret=b"x" * 32)
    assert other.email_index("player@example.com") != blind_index.email_index(
        "player@example.com"
    )


def test_ip_fingerprints_change_from_one_day_to_the_next(blind_index):
    """Yesterday's counter rows cannot be matched against today's.

    The salt rotates daily and is never stored beside the digests, so the rate
    limit counters work for the hour they are needed and are useless afterwards
    as a record of anyone's activity.
    """
    address = "203.0.113.42"  # TEST-NET-3, reserved for documentation
    monday = blind_index.ip_digest(address, now=datetime(2026, 9, 7, 12, 0, tzinfo=UTC))
    tuesday = blind_index.ip_digest(address, now=datetime(2026, 9, 8, 12, 0, tzinfo=UTC))

    assert monday != tuesday


def test_ip_fingerprints_are_stable_within_a_day(blind_index):
    """Rate limiting needs the same caller to land in the same bucket."""
    address = "203.0.113.42"
    morning = blind_index.ip_digest(address, now=datetime(2026, 9, 7, 9, 0, tzinfo=UTC))
    evening = blind_index.ip_digest(address, now=datetime(2026, 9, 7, 21, 0, tzinfo=UTC))

    assert morning == evening
