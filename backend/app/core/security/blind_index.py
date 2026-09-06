"""Keyed fingerprints: searching encrypted data, and counting without identifying.

THE PROBLEM THIS SOLVES
Login needs to find an account by email address. But email addresses are
encrypted, and good encryption produces a different result every time it runs —
that is what stops an attacker noticing that two users share an address. So
``WHERE email_ct = ?`` can never match anything.

THE SOLUTION
Store a second value: a keyed fingerprint of the address, called a *blind
index*. It is produced with HMAC-SHA256, which takes a secret key and some text
and returns 32 bytes. Feed it the same text and key and you always get the same
bytes, so it can be indexed and searched. But it cannot be run backwards, and
without the key an attacker cannot even guess-and-check.

**The key is never stored in the database.** That single fact is what stops
someone holding a stolen dump from testing whether a given address is
registered. In production it lives in AWS Secrets Manager.

WHAT THIS LEAKS, EXACTLY
Two identical addresses produce two identical fingerprints, so an attacker with
a dump learns that two accounts share an email — but not what it is. That is
the whole leak, and it is why this is called a *blind* index.

IP ADDRESSES ARE DIFFERENT
Rate limiting needs to count requests per network address, and an IP address is
personal data. So addresses are fingerprinted too — but with a salt that
changes every day and is never written down beside the digests. Today's
fingerprint for an address is unrelated to yesterday's, so the stored counters
cannot be assembled into a history of anyone's activity.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import UTC, datetime

from app.config import Settings


def normalize_email(email: str) -> str:
    """Put an email address into one canonical form before fingerprinting.

    Without this, ``Alex@Example.com`` and ``alex@example.com`` would produce
    different fingerprints and register as two separate accounts. Email domains
    are case-insensitive by specification, and every mail provider in practice
    treats the local part that way too.

    Args:
        email: The address as the user typed it.

    Returns:
        The address trimmed of surrounding whitespace and lowercased.
    """
    return email.strip().lower()


class BlindIndexService:
    """Produces keyed fingerprints for lookup and for privacy-preserving counting."""

    def __init__(self, index_key: bytes, ip_secret: bytes) -> None:
        """Set up the service with its two independent keys.

        Args:
            index_key: The key for email fingerprints. Stable forever — changing
                it invalidates every stored fingerprint and requires a rebuild.
            ip_secret: The base secret from which a fresh daily salt is derived
                for network address fingerprints.
        """
        self._index_key = index_key
        self._ip_secret = ip_secret

    @classmethod
    def from_settings(cls, settings: Settings) -> BlindIndexService:
        """Build the service from validated application settings.

        Args:
            settings: The application settings.

        Returns:
            A configured service.
        """
        return cls(
            index_key=base64.b64decode(settings.blind_index_key.get_secret_value()),
            ip_secret=base64.b64decode(settings.ip_hash_secret.get_secret_value()),
        )

    def email_index(self, email: str) -> bytes:
        """Compute the searchable fingerprint of an email address.

        Args:
            email: The address, in any capitalisation.

        Returns:
            32 bytes, suitable for the ``users.email_bidx`` column.
        """
        return hmac.new(self._index_key, normalize_email(email).encode("utf-8"), hashlib.sha256).digest()

    def username_digest(self, username: str) -> bytes:
        """Fingerprint a username for use as a rate-limiting bucket key.

        Usernames are classified as non-personal and stored in plaintext, so
        this is not a privacy measure. It exists so that every rate-limit
        bucket key is the same fixed 32 bytes regardless of what it identifies,
        which keeps the counter table uniform and leaks nothing about whether a
        given bucket counts an address or a name.

        Args:
            username: The account name.

        Returns:
            32 bytes.
        """
        return hmac.new(
            self._index_key, b"username:" + username.strip().lower().encode("utf-8"), hashlib.sha256
        ).digest()

    def _daily_salt(self, day: str) -> bytes:
        """Derive the salt for one specific day from the long-lived base secret.

        Args:
            day: The date as ``YYYY-MM-DD`` in UTC.

        Returns:
            32 bytes, deterministic for that day and unguessable without the
            base secret. Deriving rather than storing means there is no table
            of past salts for an attacker to steal, and no cleanup job to
            forget to run.
        """
        return hmac.new(self._ip_secret, f"ip-salt:{day}".encode(), hashlib.sha256).digest()

    def ip_digest(self, ip_address: str, *, now: datetime | None = None) -> bytes:
        """Fingerprint a network address for today's rate-limit counters.

        Args:
            ip_address: The caller's IP address, as text.
            now: Override the current time. Used by tests to prove that the
                digest for the same address genuinely differs across days.

        Returns:
            32 bytes that identify this address *for today only*. Tomorrow the
            same address produces an unrelated value, so yesterday's counter
            rows cannot be linked to today's.
        """
        moment = now or datetime.now(UTC)
        salt = self._daily_salt(moment.strftime("%Y-%m-%d"))
        return hmac.new(salt, ip_address.strip().encode("utf-8"), hashlib.sha256).digest()
