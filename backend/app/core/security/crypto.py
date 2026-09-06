"""Envelope encryption: turning personal data into ciphertext before it is stored.

WHERE THIS SITS
Encryption happens in the application, above the database layer. That is a
deliberate choice with a practical consequence: plaintext never travels to the
database server, so it cannot appear in query logs, slow-query logs, or a
network capture between the two clouds. By the time the database sees an email
address it is already an opaque block of bytes.

THE FORMAT OF A CIPHERTEXT VALUE
Every encrypted column holds bytes laid out like this:

    [1 byte format version][12 byte nonce][ciphertext + 16 byte tag]

The format version lets the layout change later without guessing. The nonce
("number used once") is random per value and is not secret. The tag is a
tamper check produced by AES-GCM: change any byte and decryption fails loudly
rather than returning corrupted text.

WHY EACH VALUE IS BOUND TO ITS LOCATION
Encryption includes "additional authenticated data" (AAD) naming the user, the
table and the column. AAD is not stored — it is recomputed at decryption time
and mixed into the tamper check. The effect: an attacker who copies the
encrypted email out of one user's row and pastes it into another's produces a
value that will not decrypt. Ciphertext cannot be relocated.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.security.keys import KeyProvider, KeyProviderError

CIPHERTEXT_FORMAT_VERSION = 1
NONCE_LENGTH_BYTES = 12

# How long an unwrapped key may stay in memory before it must be fetched
# again. Short enough that a revoked KMS permission takes effect quickly;
# long enough that reading a page of thirty messages costs one KMS call
# rather than thirty.
KEY_CACHE_TTL_SECONDS = 300

# A ceiling on how many users' keys are held at once, so a busy server cannot
# grow its memory without limit.
KEY_CACHE_MAX_ENTRIES = 512


class DecryptionError(RuntimeError):
    """Raised when a value cannot be decrypted.

    Always treat this as fatal for the request. There is no safe fallback: a
    failed decryption means the data is corrupt, the wrong key was used, or
    someone has tampered with the stored bytes. Returning a placeholder or an
    empty string in this situation would hide a security event.
    """


class CryptoShreddedError(RuntimeError):
    """Raised when a user's key has been destroyed by account deletion.

    This is a normal, expected outcome rather than a bug. It means the account
    was deleted and its data is now permanently unreadable — by us as much as
    by anyone else. The API turns it into a 404 Not Found, because from the
    outside the account genuinely no longer exists.
    """


@dataclass(frozen=True, slots=True)
class FieldRef:
    """Names one encrypted column, for binding ciphertext to its location.

    Attributes:
        table: The table name, e.g. ``"users"``.
        column: The column name without its ``_ct`` suffix, e.g. ``"email"``.
    """

    table: str
    column: str


@dataclass(frozen=True, slots=True)
class WrappedKey:
    """A user's Data Encryption Key as it is stored in the database.

    Attributes:
        wrapped: The encrypted key bytes, from ``users.dek_wrapped``.
        version: Which key generation wrapped it, from ``users.dek_key_version``.
            Storing this lets the master key rotate without re-encrypting every
            existing row at once.
    """

    wrapped: bytes
    version: int


class UserCipher:
    """Encrypts and decrypts for exactly one user, holding their unwrapped key.

    Deliberately scoped to a single user. There is no object anywhere in this
    codebase that can decrypt two users' data at once, which makes accidental
    cross-user leakage difficult to write.
    """

    __slots__ = ("_aead", "_key_version", "_user_id")

    def __init__(self, user_id: UUID, data_key: bytes, key_version: int) -> None:
        """Prepare a cipher bound to one user.

        Args:
            user_id: Whose data this cipher may touch.
            data_key: The unwrapped 32-byte Data Encryption Key.
            key_version: Which key generation produced it.
        """
        self._user_id = user_id
        self._key_version = key_version
        self._aead = AESGCM(data_key)

    @property
    def key_version(self) -> int:
        """Return the key generation, for storing alongside new ciphertext."""
        return self._key_version

    def _aad(self, field: FieldRef) -> bytes:
        """Build the additional authenticated data binding a value to its home.

        Args:
            field: Which table and column the value belongs to.

        Returns:
            The AAD bytes. Not stored anywhere — recomputed on decryption.
        """
        return f"v1|{self._user_id}|{field.table}|{field.column}".encode()

    def encrypt(self, field: FieldRef, plaintext: str) -> bytes:
        """Encrypt a piece of text for storage.

        Args:
            field: Which column this value is destined for.
            plaintext: The text to protect.

        Returns:
            The bytes to store in the ``_ct`` column.
        """
        nonce = os.urandom(NONCE_LENGTH_BYTES)
        body = self._aead.encrypt(nonce, plaintext.encode("utf-8"), self._aad(field))
        return bytes([CIPHERTEXT_FORMAT_VERSION]) + nonce + body

    def decrypt(self, field: FieldRef, stored: bytes) -> str:
        """Recover text from a stored ciphertext value.

        Args:
            field: Which column the value came from. Must match the column it
                was encrypted for, or the tamper check fails.
            stored: The bytes read from the database.

        Returns:
            The original text.

        Raises:
            DecryptionError: If the value is malformed, was encrypted for a
                different location, was encrypted for a different user, or has
                been modified since it was written.
        """
        if len(stored) < 1 + NONCE_LENGTH_BYTES:
            raise DecryptionError(
                f"Stored value for {field.table}.{field.column} is too short to be ciphertext."
            )
        version = stored[0]
        if version != CIPHERTEXT_FORMAT_VERSION:
            raise DecryptionError(
                f"Stored value for {field.table}.{field.column} uses unknown ciphertext "
                f"format {version}; this build understands {CIPHERTEXT_FORMAT_VERSION}."
            )
        nonce = stored[1 : 1 + NONCE_LENGTH_BYTES]
        body = stored[1 + NONCE_LENGTH_BYTES :]
        try:
            return self._aead.decrypt(nonce, body, self._aad(field)).decode("utf-8")
        except InvalidTag as exc:
            raise DecryptionError(
                f"Failed to decrypt {field.table}.{field.column}. Either the wrong key was "
                "used, the value was moved from another row or column, or it has been "
                "tampered with. No fallback is attempted."
            ) from exc

    def encrypt_json(self, field: FieldRef, value: Any) -> bytes:
        """Encrypt a structured value, such as a character sheet.

        Args:
            field: Which column this value is destined for.
            value: Any JSON-serialisable object.

        Returns:
            The bytes to store.
        """
        return self.encrypt(field, json.dumps(value, separators=(",", ":"), sort_keys=True))

    def decrypt_json(self, field: FieldRef, stored: bytes) -> Any:
        """Recover a structured value from ciphertext.

        Args:
            field: Which column the value came from.
            stored: The bytes read from the database.

        Returns:
            The decoded object.

        Raises:
            DecryptionError: If decryption fails, or if the decrypted text is
                not valid JSON — which would mean the stored value is corrupt.
        """
        text = self.decrypt(field, stored)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise DecryptionError(
                f"{field.table}.{field.column} decrypted successfully but is not valid JSON."
            ) from exc


class EncryptionService:
    """Creates and caches per-user ciphers, wrapping and unwrapping keys.

    This is the single object the rest of the application asks for encryption.
    It hides the difference between the development key provider and AWS KMS,
    and it caches unwrapped keys briefly so that reading a page of messages
    does not mean one key-service call per message.
    """

    def __init__(self, provider: KeyProvider) -> None:
        """Set up the service.

        Args:
            provider: The key provider chosen by configuration.
        """
        self._provider = provider
        # Maps user id to (cipher, expiry timestamp).
        self._cache: dict[UUID, tuple[UserCipher, float]] = {}

    def create_user_key(self, user_id: UUID) -> tuple[WrappedKey, UserCipher]:
        """Mint a brand new Data Encryption Key for a newly registered user.

        Args:
            user_id: The new account's identifier.

        Returns:
            The wrapped key to store in the database, and a ready cipher.
        """
        plaintext, wrapped = self._provider.generate_data_key()
        cipher = UserCipher(user_id, plaintext, key_version=1)
        self._cache[user_id] = (cipher, time.monotonic() + KEY_CACHE_TTL_SECONDS)
        return WrappedKey(wrapped=wrapped, version=1), cipher

    def cipher_for(self, user_id: UUID, key: WrappedKey | None) -> UserCipher:
        """Get a cipher for a user, unwrapping their key if it is not cached.

        Args:
            user_id: Whose data is being read or written.
            key: The wrapped key from their row, or ``None`` if the account has
                been crypto-shredded.

        Returns:
            A cipher scoped to that user.

        Raises:
            CryptoShreddedError: If ``key`` is ``None``, meaning the account was
                deleted and its data is permanently unreadable.
            KeyProviderError: If the key service refuses to unwrap the key.
        """
        if key is None:
            raise CryptoShreddedError(
                f"User {user_id} has no data key. The account was deleted and its data "
                "is permanently unrecoverable — this is crypto-shredding working "
                "as designed, not a fault."
            )

        cached = self._cache.get(user_id)
        now = time.monotonic()
        if cached is not None and cached[1] > now:
            return cached[0]

        plaintext = self._provider.unwrap_data_key(key.wrapped)
        cipher = UserCipher(user_id, plaintext, key_version=key.version)
        self._evict_if_full()
        self._cache[user_id] = (cipher, now + KEY_CACHE_TTL_SECONDS)
        return cipher

    def forget(self, user_id: UUID) -> None:
        """Drop a user's cached key immediately.

        Called on account deletion so that a cached key cannot keep serving
        decryptions for up to five minutes after the account is shredded.

        Args:
            user_id: Whose cached key to discard.
        """
        self._cache.pop(user_id, None)

    def _evict_if_full(self) -> None:
        """Make room in the cache by discarding the entries closest to expiry.

        Keys are cheap to re-fetch, so eviction is a performance question, not
        a correctness one.
        """
        if len(self._cache) < KEY_CACHE_MAX_ENTRIES:
            return
        oldest = sorted(self._cache.items(), key=lambda item: item[1][1])
        for user_id, _ in oldest[: KEY_CACHE_MAX_ENTRIES // 4]:
            self._cache.pop(user_id, None)


__all__ = [
    "CryptoShreddedError",
    "DecryptionError",
    "EncryptionService",
    "FieldRef",
    "KeyProviderError",
    "UserCipher",
    "WrappedKey",
]
