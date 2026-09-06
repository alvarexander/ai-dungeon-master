"""Tests for envelope encryption — the foundation of the whole privacy design.

These run the real cryptography against the local development key. Nothing is
mocked, because a mock of encryption would prove nothing at all.
"""

from __future__ import annotations

import uuid

import pytest

from app.core.security.crypto import (
    CryptoShreddedError,
    DecryptionError,
    FieldRef,
)

EMAIL_FIELD = FieldRef("users", "email")
NAME_FIELD = FieldRef("characters", "name")


def test_encrypt_then_decrypt_returns_the_original(encryption):
    """Text survives a round trip through encryption unchanged."""
    user_id = uuid.uuid4()
    _, cipher = encryption.create_user_key(user_id)

    ciphertext = cipher.encrypt(EMAIL_FIELD, "player@example.com")
    assert cipher.decrypt(EMAIL_FIELD, ciphertext) == "player@example.com"


def test_ciphertext_does_not_contain_the_plaintext(encryption):
    """The stored bytes contain no trace of the original text.

    The obvious check, and worth making explicitly: if this ever failed, every
    other guarantee in the system would be worthless.
    """
    _, cipher = encryption.create_user_key(uuid.uuid4())
    ciphertext = cipher.encrypt(EMAIL_FIELD, "player@example.com")

    assert b"player" not in ciphertext
    assert b"example.com" not in ciphertext


def test_same_text_encrypts_differently_every_time(encryption):
    """Encrypting identical text twice produces different ciphertext.

    This is what stops an attacker with a database dump noticing that two users
    share an email address. It is also precisely why a blind index is needed
    for login — you cannot search for something that never looks the same twice.
    """
    _, cipher = encryption.create_user_key(uuid.uuid4())

    first = cipher.encrypt(EMAIL_FIELD, "player@example.com")
    second = cipher.encrypt(EMAIL_FIELD, "player@example.com")

    assert first != second
    assert cipher.decrypt(EMAIL_FIELD, first) == cipher.decrypt(EMAIL_FIELD, second)


def test_ciphertext_cannot_be_moved_to_another_column(encryption):
    """A value encrypted for one column will not decrypt as another.

    This is the additional authenticated data doing its job. An attacker who
    copies the encrypted email into the character-name column gets a value that
    fails to decrypt, rather than one that silently succeeds.
    """
    _, cipher = encryption.create_user_key(uuid.uuid4())
    ciphertext = cipher.encrypt(EMAIL_FIELD, "player@example.com")

    with pytest.raises(DecryptionError):
        cipher.decrypt(NAME_FIELD, ciphertext)


def test_ciphertext_cannot_be_moved_to_another_user(encryption):
    """A value encrypted for one user will not decrypt for another."""
    _, alice_cipher = encryption.create_user_key(uuid.uuid4())
    _, bob_cipher = encryption.create_user_key(uuid.uuid4())

    ciphertext = alice_cipher.encrypt(EMAIL_FIELD, "player@example.com")

    with pytest.raises(DecryptionError):
        bob_cipher.decrypt(EMAIL_FIELD, ciphertext)


def test_tampering_is_detected(encryption):
    """Changing a single byte makes decryption fail rather than return rubbish.

    AES-GCM includes a tamper check. Without it, an attacker could flip bits in
    stored ciphertext and the application would decrypt the result into
    corrupted text without noticing.
    """
    _, cipher = encryption.create_user_key(uuid.uuid4())
    ciphertext = bytearray(cipher.encrypt(EMAIL_FIELD, "player@example.com"))
    ciphertext[-1] ^= 0x01  # flip one bit in the final byte

    with pytest.raises(DecryptionError):
        cipher.decrypt(EMAIL_FIELD, bytes(ciphertext))


def test_structured_data_round_trips(encryption):
    """A character sheet survives encryption and decryption intact."""
    _, cipher = encryption.create_user_key(uuid.uuid4())
    sheet = {"abilities": {"strength": 12, "dexterity": 16}, "inventory": ["a rope", "a lantern"]}

    stored = cipher.encrypt_json(FieldRef("characters", "sheet"), sheet)
    assert cipher.decrypt_json(FieldRef("characters", "sheet"), stored) == sheet


def test_a_shredded_user_cannot_be_decrypted(encryption):
    """Once the key is gone, the data is unreadable — permanently.

    This is crypto-shredding stated as a test. ``None`` in place of a wrapped
    key is exactly what account deletion leaves behind, and the only possible
    outcome is a refusal.
    """
    user_id = uuid.uuid4()

    with pytest.raises(CryptoShreddedError):
        encryption.cipher_for(user_id, None)


def test_wrapped_key_is_not_the_key(encryption):
    """What gets stored in the database is the wrapped key, not a usable one.

    The wrapped key is what sits in ``users.dek_wrapped``. An attacker holding
    a database dump holds these bytes and nothing else — unwrapping them
    requires the key service, which is not in the database.
    """
    user_id = uuid.uuid4()
    wrapped, cipher = encryption.create_user_key(user_id)

    ciphertext = cipher.encrypt(EMAIL_FIELD, "player@example.com")
    # The wrapped key must not simply be the raw key sitting in the open.
    assert wrapped.wrapped not in ciphertext
    assert len(wrapped.wrapped) > 32  # nonce plus ciphertext plus tag

    # And it does round-trip through the key service, proving it is real.
    recovered = encryption.cipher_for(user_id, wrapped)
    assert recovered.decrypt(EMAIL_FIELD, ciphertext) == "player@example.com"
