"""Domain objects and the repository contracts that store them.

WHAT A REPOSITORY IS AND WHY IT MATTERS HERE
A repository is the only code allowed to touch storage. Everything above it —
the game rules, the endpoints — works with ordinary Python objects and never
writes a line of SQL.

In most projects that is a tidiness argument. Here it is a security control.
Encryption happens inside the repository, on the way in and out. Because the
repository is the *only* door to storage, it is impossible to save a user's
email without passing through the code that encrypts it. Correctness stops
depending on whether whoever writes the next endpoint remembers to encrypt —
there is no path that skips it.

WHERE THIS SITS RELATIVE TO THE DATABASE LAYER
Above it. The domain objects below hold plaintext. The repository converts them
to ciphertext and hands the ciphertext to storage. So plaintext never travels
to the database server, never appears in a query log, and never crosses the
network between Fly.io and AWS.

PHASE 1 AND PHASE 2
`app/repositories/memory.py` implements these contracts in memory. Phase 2 adds
a SQL implementation. Both encrypt identically, at the same boundary; only the
place the ciphertext lands differs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from app.schemas.settings import UserSettings


def utc_now() -> datetime:
    """Return the current time in UTC.

    Every timestamp in this application is UTC. Storing local times is a
    recurring source of bugs the moment a server moves region or daylight
    saving changes.

    Returns:
        The current moment, timezone-aware, in UTC.
    """
    return datetime.now(UTC)


@dataclass(slots=True)
class User:
    """One account, with personal fields in plaintext.

    This object only ever exists in memory, inside a request. The repository
    encrypts every field marked below before anything is stored.
    """

    user_id: UUID
    username: str  # plaintext by classification
    display_name: str  # plaintext by classification
    email: str  # ENCRYPTED at rest
    password_hash: str  # HASHED, never encrypted
    email_verified: bool = False
    created_at: datetime = field(default_factory=utc_now)
    status: str = "active"
    settings: UserSettings = field(default_factory=UserSettings)
    is_stub: bool = True


@dataclass(slots=True)
class Campaign:
    """One ongoing story."""

    campaign_id: UUID
    user_id: UUID
    title: str  # ENCRYPTED at rest
    premise: str | None  # ENCRYPTED at rest
    ruleset: str = "dnd5e"
    tone: str = "heroic"
    status: str = "active"
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Character:
    """One player character."""

    character_id: UUID
    campaign_id: UUID
    user_id: UUID
    name: str  # ENCRYPTED at rest
    character_class: str  # plaintext, not personal
    level: int  # plaintext, not personal
    sheet: dict[str, Any]  # ENCRYPTED at rest, stored as JSON
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class GameSession:
    """One sitting at the table."""

    game_session_id: UUID
    campaign_id: UUID
    user_id: UUID
    started_at: datetime = field(default_factory=utc_now)
    ended_at: datetime | None = None
    turn_count: int = 0
    debug_capture: bool = False
    debug_capture_until: datetime | None = None


@dataclass(slots=True)
class Message:
    """One line of the transcript.

    ``content`` is personal data. Players type their own names, their friends'
    names, and whatever else into it, which is why it is encrypted with the
    same care as an email address.
    """

    message_id: UUID
    game_session_id: UUID
    user_id: UUID
    seq: int
    role: str
    content: str  # ENCRYPTED at rest
    input_mode: str = "typed"
    token_count: int = 0
    created_at: datetime = field(default_factory=utc_now)


class UserRepository(Protocol):
    """Storage operations for accounts."""

    async def create(self, user: User, password_hash: str) -> User:
        """Store a new account, minting its encryption key.

        Args:
            user: The account to store.
            password_hash: The Argon2id digest.

        Returns:
            The stored account.
        """
        ...

    async def get(self, user_id: UUID) -> User | None:
        """Fetch an account by identifier, decrypting its fields.

        Args:
            user_id: Which account.

        Returns:
            The account, or ``None`` if it does not exist.
        """
        ...

    async def find_by_email(self, email: str) -> User | None:
        """Find an account by email address.

        The email is converted to a blind index fingerprint first; the stored
        addresses are never compared directly, because they are ciphertext.

        Args:
            email: The address to look up.

        Returns:
            The account, or ``None``.
        """
        ...

    async def find_by_username(self, username: str) -> User | None:
        """Find an account by username.

        Args:
            username: The handle to look up.

        Returns:
            The account, or ``None``.
        """
        ...

    async def update_settings(self, user_id: UUID, settings: UserSettings) -> UserSettings:
        """Replace a user's preferences.

        Args:
            user_id: Which account.
            settings: The complete new settings.

        Returns:
            The stored settings.
        """
        ...

    async def crypto_shred(self, user_id: UUID) -> datetime:
        """Destroy the account's encryption key, rendering its data unreadable.

        Args:
            user_id: Which account.

        Returns:
            When the key was destroyed.
        """
        ...


class CampaignRepository(Protocol):
    """Storage operations for campaigns."""

    async def create(self, campaign: Campaign) -> Campaign:
        """Store a new campaign.

        Args:
            campaign: The campaign to store.

        Returns:
            The stored campaign.
        """
        ...

    async def get(self, user_id: UUID, campaign_id: UUID) -> Campaign | None:
        """Fetch one campaign belonging to a user.

        Args:
            user_id: The owner. Always required, so a caller cannot read
                someone else's campaign by guessing an identifier.
            campaign_id: Which campaign.

        Returns:
            The campaign, or ``None``.
        """
        ...

    async def list_for_user(self, user_id: UUID, limit: int, offset: int) -> tuple[list[Campaign], int]:
        """List a user's campaigns, newest activity first.

        Args:
            user_id: The owner.
            limit: Page size.
            offset: How many to skip.

        Returns:
            The page of campaigns and the total count.
        """
        ...

    async def update(self, campaign: Campaign) -> Campaign:
        """Save changes to a campaign.

        Args:
            campaign: The campaign with its new values.

        Returns:
            The stored campaign.
        """
        ...

    async def delete(self, user_id: UUID, campaign_id: UUID) -> bool:
        """Remove a campaign.

        Args:
            user_id: The owner.
            campaign_id: Which campaign.

        Returns:
            True if something was removed.
        """
        ...


class CharacterRepository(Protocol):
    """Storage operations for characters."""

    async def create(self, character: Character) -> Character:
        """Store a new character.

        Args:
            character: The character to store.

        Returns:
            The stored character.
        """
        ...

    async def get(self, user_id: UUID, character_id: UUID) -> Character | None:
        """Fetch one character belonging to a user.

        Args:
            user_id: The owner.
            character_id: Which character.

        Returns:
            The character, or ``None``.
        """
        ...

    async def list_for_campaign(self, user_id: UUID, campaign_id: UUID) -> list[Character]:
        """List every character in a campaign.

        Args:
            user_id: The owner.
            campaign_id: Which campaign.

        Returns:
            The characters.
        """
        ...

    async def update(self, character: Character) -> Character:
        """Save changes to a character.

        Args:
            character: The character with its new values.

        Returns:
            The stored character.
        """
        ...

    async def delete(self, user_id: UUID, character_id: UUID) -> bool:
        """Remove a character.

        Args:
            user_id: The owner.
            character_id: Which character.

        Returns:
            True if something was removed.
        """
        ...


class SessionRepository(Protocol):
    """Storage operations for play sessions and their transcripts."""

    async def create_session(self, session: GameSession) -> GameSession:
        """Start a new play session.

        Args:
            session: The session to store.

        Returns:
            The stored session.
        """
        ...

    async def get_session(self, user_id: UUID, session_id: UUID) -> GameSession | None:
        """Fetch one session belonging to a user.

        Args:
            user_id: The owner.
            session_id: Which session.

        Returns:
            The session, or ``None``.
        """
        ...

    async def append_message(self, message: Message) -> Message:
        """Add one message to a transcript, assigning its sequence number.

        Args:
            message: The message to store. Its ``seq`` is assigned here so that
                two concurrent requests cannot claim the same position.

        Returns:
            The stored message, with its sequence number set.
        """
        ...

    async def list_messages(
        self, user_id: UUID, session_id: UUID, after_seq: int, limit: int
    ) -> list[Message]:
        """Read a page of a transcript, decrypting each message.

        Args:
            user_id: The owner.
            session_id: Which session.
            after_seq: Return messages after this position.
            limit: Page size.

        Returns:
            The messages, in order.
        """
        ...

    async def set_debug_capture(self, user_id: UUID, session_id: UUID, enabled: bool) -> GameSession | None:
        """Turn the opt-in prompt capture on or off for a session.

        Args:
            user_id: The owner.
            session_id: Which session.
            enabled: Whether to capture.

        Returns:
            The updated session, or ``None`` if it does not exist.
        """
        ...
