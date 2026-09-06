"""Registration, sign-in, and the account lifecycle.

═══════════════════════════════════════════════════════════════════════
WHAT IS REAL HERE AND WHAT IS STUBBED — read this before trusting it
═══════════════════════════════════════════════════════════════════════
The brief asked for authentication screens to be built but their calls stubbed.
Rather than fake the whole thing, the split was drawn where it is genuinely
useful, and this is exactly where it falls:

**Genuinely implemented, running the production code path:**
  - Passwords hashed with Argon2id, and verified against that hash.
  - Email addresses encrypted with a per-user key at registration.
  - Email lookup by blind index, never by comparing addresses.
  - Timing equalisation, so an unknown account takes as long as a known one.
  - Uniform error messages, so responses never reveal who is registered.
  - Rate limiting on both registration and sign-in.
  - Account deletion by crypto-shredding.

**Deliberately stubbed:**
  - **The session token.** ``issue_token`` returns ``stub.<user_id>``, and
    ``user_id_from_token`` believes it. Anyone can mint one for any account.
    There is no signature, no expiry, no revocation.

That single stub is why ``AUTH_MODE=stub`` causes the application to refuse to
start when ``APP_ENV=production``. The screens can be clicked through today;
the door is not actually locked, and the application will not pretend
otherwise on a real server.

Phase 2 replaces only ``issue_token`` and ``user_id_from_token`` with signed,
expiring tokens backed by the ``user_sessions`` table. Nothing else in this
file changes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.core.errors import ApiError, AuthenticationError
from app.core.logging import get_logger
from app.core.security.passwords import hash_password, verify_dummy, verify_password
from app.repositories.base import User
from app.repositories.memory import MemoryUserRepository, new_id
from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.settings import UserSettings

_log = get_logger("auth")

STUB_TOKEN_PREFIX = "stub."

# The account the frontend uses before anyone signs in, so that the chat works
# the moment the server starts. Created by the seed script and at startup.
DEMO_USERNAME = "demo-adventurer"
DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo-passphrase-not-secret"  # noqa: S105 - a local fixture, published deliberately


class AuthService:
    """Creates accounts, verifies credentials, and deletes accounts."""

    def __init__(self, users: MemoryUserRepository) -> None:
        """Set up the service.

        Args:
            users: The account repository, which handles encryption.
        """
        self._users = users

    async def register(self, request: RegisterRequest) -> User:
        """Create a new account.

        Everything privacy-relevant here is real: the password is hashed with
        Argon2id and never stored, the email is encrypted under a key minted
        for this account alone, and only a keyed fingerprint of the address is
        searchable.

        Args:
            request: The validated registration details.

        Returns:
            The created account.

        Raises:
            ApiError: If the username or email is already in use. Note the
                wording of that error: it is deliberately identical for both
                cases, so registration cannot be used to discover which email
                addresses already have accounts — the same enumeration risk the
                encrypted email column exists to close.
        """
        user = User(
            user_id=new_id(),
            username=request.username,
            display_name=request.display_name,
            email=request.email,
            password_hash=hash_password(request.password),
            settings=UserSettings(),
        )
        try:
            created = await self._users.create(user, user.password_hash)
        except ValueError as exc:
            _log.info("registration_rejected", reason_code=str(exc))
            raise ApiError(
                status_code=409,
                code="registration_conflict",
                message=(
                    "That username or email address cannot be used. If you already have "
                    "an account, try signing in instead."
                ),
            ) from exc

        _log.info("registration_completed", user_id=str(created.user_id))
        return created

    async def authenticate(self, request: LoginRequest) -> User:
        """Check credentials and return the account, or refuse.

        Two protections are worth pointing out because they are easy to omit
        and hard to add later:

        1. **Identical failure.** Whether the account does not exist, the
           password is wrong, or the account is suspended, the caller gets the
           same error. Anything more specific is a map of who is registered.
        2. **Identical timing.** When no account matches, the password is still
           verified — against a throwaway hash. Without this, an unknown
           address would return in a millisecond and a known one in three
           hundred, and an attacker could enumerate accounts with a stopwatch.

        Args:
            request: The submitted credentials.

        Returns:
            The authenticated account.

        Raises:
            AuthenticationError: On any failure, always with the same message.
        """
        identifier = request.identifier.strip()
        if "@" in identifier:
            user = await self._users.find_by_email(identifier)
        else:
            user = await self._users.find_by_username(identifier)

        if user is None:
            verify_dummy(request.password)
            _log.info("login_failed", reason_code="no_account")
            raise AuthenticationError()

        if not verify_password(user.password_hash, request.password):
            _log.info("login_failed", reason_code="bad_password", user_id=str(user.user_id))
            raise AuthenticationError()

        if user.status != "active":
            _log.info("login_failed", reason_code="inactive", user_id=str(user.user_id))
            raise AuthenticationError()

        _log.info("login_succeeded", user_id=str(user.user_id))
        return user

    async def delete_account(self, user_id: UUID) -> datetime:
        """Delete an account by destroying its encryption key.

        This is crypto-shredding. It does not go through the data deleting it;
        it destroys the only key that can read it. Every encrypted byte
        belonging to this account — live, in last night's backup, in a copy an
        attacker may already hold — becomes permanently unreadable at the
        moment this returns.

        Args:
            user_id: Which account to destroy.

        Returns:
            When the key was destroyed.

        Raises:
            ApiError: If the account does not exist.
        """
        try:
            shredded_at = await self._users.crypto_shred(user_id)
        except KeyError as exc:
            raise ApiError(404, "not_found", "That account could not be found.") from exc
        _log.info("account_crypto_shredded", user_id=str(user_id))
        return shredded_at

    # -----------------------------------------------------------------
    # The stubbed part. Everything above is production code.
    # -----------------------------------------------------------------

    @staticmethod
    def issue_token(user: User) -> str:
        """Issue a session token. **STUB — not a real credential.**

        Returns an unsigned string containing the account identifier. There is
        no signature, no expiry, and no way to revoke it. Anyone can construct
        one for any account by typing it.

        Phase 2 replaces this with a signed, expiring token recorded in the
        ``user_sessions`` table, where only a hash of the token is stored so
        that a database leak does not hand over working sessions.

        Args:
            user: The authenticated account.

        Returns:
            A placeholder token, prefixed ``stub.`` so it is obvious in any log
            or network capture that this is not a real credential.
        """
        return f"{STUB_TOKEN_PREFIX}{user.user_id}"

    @staticmethod
    def user_id_from_token(token: str) -> UUID | None:
        """Read the account identifier out of a token. **STUB — trusts it.**

        Performs no verification whatsoever, because there is nothing to
        verify. See the module docstring.

        Args:
            token: The bearer token from the Authorization header.

        Returns:
            The claimed account identifier, or ``None`` if the token is not
            even shaped correctly.
        """
        if not token.startswith(STUB_TOKEN_PREFIX):
            return None
        try:
            return UUID(token[len(STUB_TOKEN_PREFIX) :])
        except ValueError:
            return None


async def ensure_demo_user(users: MemoryUserRepository) -> User:
    """Create the demo account if it does not already exist.

    Phase 1 keeps everything in memory, so a restart empties the application.
    This runs at startup so that the frontend has a working account
    immediately and the chat can be tried without registering first.

    Args:
        users: The account repository.

    Returns:
        The demo account.
    """
    existing = await users.find_by_username(DEMO_USERNAME)
    if existing is not None:
        return existing

    user = User(
        user_id=new_id(),
        username=DEMO_USERNAME,
        display_name="Demo Adventurer",
        email=DEMO_EMAIL,
        password_hash=hash_password(DEMO_PASSWORD),
        created_at=datetime.now(UTC),
        settings=UserSettings(),
    )
    await users.create(user, user.password_hash)
    _log.info("demo_user_created", user_id=str(user.user_id))
    return user
