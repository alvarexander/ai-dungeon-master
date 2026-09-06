"""Password hashing with Argon2id.

HASHING IS NOT ENCRYPTION, AND THE DIFFERENCE MATTERS HERE MOST
Encryption is reversible: you encrypt, and later you decrypt back to the
original. Hashing is not: you hash, and there is no way back. You can only take
a guess, hash the guess, and see whether the two results match.

Passwords must never be readable — not by an attacker, not by the database, not
by you. So they are hashed. If they were encrypted instead, anyone who obtained
the key would recover every password in plaintext, and because people reuse
passwords you would have handed over their email and bank logins too. Encrypted
passwords are a security defect, not a style choice.

WHY ARGON2id RATHER THAN SOMETHING FASTER
A fast hash is a liability. An attacker with a stolen database tries billions of
guesses per second on specialised hardware. Argon2id is deliberately slow *and*
deliberately memory-hungry, and the memory requirement is what defeats that
hardware — you can fit thousands of tiny fast circuits on a chip, but not
thousands of copies of 64 megabytes of memory. Argon2 won the Password Hashing
Competition in 2015 and is OWASP's current recommendation.

THE SALT IS AUTOMATIC
A "salt" is random data mixed into each password before hashing, so that two
users with the same password get different hashes and an attacker cannot attack
them both at once. The library generates one per password and stores it inside
the resulting string; there is nothing for us to manage.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2 import exceptions as argon2_exceptions

# OWASP's recommended baseline, tuned for a small server.
#   time_cost   how many passes over memory  (more = slower = safer)
#   memory_cost how much memory, in kibibytes (65536 = 64 MB)
#   parallelism how many threads
# 64 MB per hash is the number to watch: it is charged per concurrent login,
# so it interacts directly with the memory size of the Fly.io machine.
_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=2,
    hash_len=32,
    salt_len=16,
)

# A pre-computed hash of a value nobody will ever use. Explained in
# `verify_dummy` below.
_DUMMY_HASH = _HASHER.hash("not-a-real-password-used-only-for-timing-equalisation")


def hash_password(password: str) -> str:
    """Turn a password into a storable Argon2id digest.

    Args:
        password: The password exactly as the user typed it. Never logged,
            never stored, and discarded as soon as this function returns.

    Returns:
        A string containing the algorithm, its parameters, the generated salt
        and the digest — everything needed to check a future guess. Safe to
        store in ``users.password_hash``.
    """
    return _HASHER.hash(password)


def verify_password(stored_hash: str, candidate: str) -> bool:
    """Check whether a typed password matches a stored digest.

    Args:
        stored_hash: The value from ``users.password_hash``.
        candidate: What the user just typed.

    Returns:
        True if they match, False otherwise. A malformed stored hash returns
        False rather than raising, because at the login endpoint every failure
        must look identical from the outside — a distinct error for corrupt
        data would tell an attacker something about the account.
    """
    try:
        return _HASHER.verify(stored_hash, candidate)
    except (
        argon2_exceptions.VerifyMismatchError,
        argon2_exceptions.VerificationError,
        argon2_exceptions.InvalidHashError,
    ):
        return False


def verify_dummy(candidate: str) -> bool:
    """Spend the same time verifying as a real check, for accounts that do not exist.

    THE ATTACK THIS PREVENTS
    If login rejects an unknown email instantly but takes 300 milliseconds for
    a known one, an attacker learns which addresses are registered simply by
    timing the responses. That is user enumeration through a side channel, and
    it defeats the point of encrypting the address in the first place.

    So when no account matches, the login endpoint verifies against this
    throwaway hash instead. The work done — and therefore the time taken — is
    the same either way.

    Args:
        candidate: The submitted password, which is genuinely checked against a
            hash of an unrelated value and therefore always fails.

    Returns:
        Always False.
    """
    verify_password(_DUMMY_HASH, candidate)
    return False


def needs_rehash(stored_hash: str) -> bool:
    """Report whether a stored hash was made with weaker settings than current.

    Hardware gets faster, so the recommended cost parameters rise over time.
    When they do, this returns True for old hashes and the login endpoint
    quietly re-hashes the password it has just verified. Users are upgraded as
    they log in, with no password reset and no announcement.

    Args:
        stored_hash: The value from the database.

    Returns:
        True if the password should be re-hashed after a successful login.
    """
    try:
        return _HASHER.check_needs_rehash(stored_hash)
    except argon2_exceptions.InvalidHashError:
        return True
