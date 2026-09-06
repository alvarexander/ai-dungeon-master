"""Domain objects and the repository contracts that store them.

WHAT A REPOSITORY IS

A repository is the only code allowed to touch storage. Everything above it —
the game rules, the endpoints — works with ordinary Python objects and never
writes a line of SQL.

That keeps storage decisions in one place. Swapping the in-memory store for
MySQL changes only the classes in this folder; no service and no endpoint is
aware it happened.

TWO IMPLEMENTATIONS

`memory.py` keeps everything in dictionaries and needs nothing installed. It is
the default, and it loses everything on restart.

`sql.py` stores rows in MySQL. Set `REPOSITORY_BACKEND=mysql` to use it; see
`docs/LOCAL_MYSQL.md` for installing MySQL locally.

A NOTE ON OWNERSHIP CHECKS

Every method that fetches something takes a `user_id` as well as the thing's
own identifier, and checks both. That is what stops somebody reading another
person's campaign by guessing an identifier, and it is why the interfaces look
slightly repetitive.
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
    encrypts every field marked below before anything is stored, so the
    database never sees a readable email address.
    """

    user_id: UUID
    username: str  # plaintext by classification
    display_name: str  # plaintext by classification
    email: str
    password_hash: str  # Argon2id digest. The password itself is never stored.
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
    title: str
    premise: str | None
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
    name: str
    character_class: str
    level: int
    sheet: dict[str, Any]  # stored as JSON
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


@dataclass(slots=True)
class Message:
    """One line of the transcript.

    ``content`` is what the player and the Dungeon Master actually said.
    """

    message_id: UUID
    game_session_id: UUID
    user_id: UUID
    seq: int
    role: str
    content: str
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

    async def delete(self, user_id: UUID) -> datetime:
        """Delete an account and everything belonging to it.

        Campaigns, characters, sessions and messages all go with it, through
        the ``ON DELETE CASCADE`` rules in the schema. There is nothing left
        afterwards.

        Args:
            user_id: Which account.

        Returns:
            When the deletion happened.
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

