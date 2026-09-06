"""In-memory storage for local development.

WHAT THIS IS

A set of Python dictionaries standing in for database tables. It needs nothing
installed, which makes it the right default for getting the application running
in one command.

**Everything is lost when the server restarts.** There is no file and no
database. That is expected here — run `scripts/seed_dev_data.py` to get
populated demo accounts back in one command.

WHEN TO USE THE REAL DATABASE INSTEAD

Set `REPOSITORY_BACKEND=mysql` once you want data to survive a restart.
`docs/LOCAL_MYSQL.md` walks through installing MySQL locally. Both
implementations satisfy the same interfaces in `base.py`, so nothing above this
layer changes when you switch.

A NOTE ON HOW DATA IS PROTECTED

Personal data is stored as ordinary readable values, here and in MySQL.
Protection comes from the layers around it: passwords are hashed with Argon2id
and never stored, the connection to the database uses TLS, access is
restricted by firewall, and the database provider encrypts its disks. That is
the same posture as most well-built web applications.

What it means concretely: **anyone with database access can read email
addresses and conversations.** Keep database credentials as carefully as you
would keep a password. See `docs/SECURITY.md`.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.repositories.base import (
    Campaign,
    Character,
    GameSession,
    Message,
    User,
    utc_now,
)
from app.schemas.settings import UserSettings


def normalize_email(email: str) -> str:
    """Put an email address into one canonical form for lookups.

    Without this, ``Alex@Example.com`` and ``alex@example.com`` would register
    as two separate accounts. Email domains are case-insensitive by
    specification, and every mail provider in practice treats the local part
    that way too.

    Args:
        email: The address as the user typed it.

    Returns:
        The address trimmed and lowercased.
    """
    return email.strip().lower()


class MemoryStore:
    """The shared in-memory tables. One instance for the whole application."""

    def __init__(self) -> None:
        """Create empty tables."""
        self.users: dict[UUID, dict[str, Any]] = {}
        self.email_index: dict[str, UUID] = {}
        self.username_index: dict[str, UUID] = {}
        self.campaigns: dict[UUID, dict[str, Any]] = {}
        self.characters: dict[UUID, dict[str, Any]] = {}
        self.sessions: dict[UUID, dict[str, Any]] = {}
        self.messages: dict[UUID, dict[str, Any]] = {}
        # Guards sequence-number assignment, the one place two concurrent
        # requests could otherwise collide.
        self.lock = asyncio.Lock()

    def clear(self) -> None:
        """Empty every table. Used by tests and by the seed script."""
        self.users.clear()
        self.email_index.clear()
        self.username_index.clear()
        self.campaigns.clear()
        self.characters.clear()
        self.sessions.clear()
        self.messages.clear()


class MemoryUserRepository:
    """Accounts."""

    def __init__(self, store: MemoryStore) -> None:
        """Set up the repository.

        Args:
            store: The shared in-memory tables.
        """
        self._store = store

    async def create(self, user: User, password_hash: str) -> User:
        """Store a new account.

        Args:
            user: The account to store.
            password_hash: The Argon2id digest of their password. The password
                itself is never stored, in any form.

        Returns:
            The stored account.

        Raises:
            ValueError: If the username or email is already taken.
        """
        email = normalize_email(user.email)
        if email in self._store.email_index:
            raise ValueError("email_taken")
        if user.username.lower() in self._store.username_index:
            raise ValueError("username_taken")

        self._store.users[user.user_id] = {
            "username": user.username,
            "display_name": user.display_name,
            "email": email,
            "email_verified": user.email_verified,
            "created_at": user.created_at,
            "status": "active",
            "settings": user.settings.model_dump(),
            # Hashed, one way. This is the one value that is never recoverable.
            "password_hash": password_hash,
        }
        self._store.email_index[email] = user.user_id
        self._store.username_index[user.username.lower()] = user.user_id
        return user

    def _hydrate(self, user_id: UUID, row: dict[str, Any]) -> User:
        """Turn a stored row back into a domain object.

        Args:
            user_id: Which account the row belongs to.
            row: The stored row.

        Returns:
            The account.
        """
        return User(
            user_id=user_id,
            username=row["username"],
            display_name=row["display_name"],
            email=row["email"],
            password_hash=row["password_hash"],
            email_verified=row["email_verified"],
            created_at=row["created_at"],
            status=row["status"],
            settings=UserSettings(**row["settings"]),
        )

    async def get(self, user_id: UUID) -> User | None:
        """Fetch an account.

        Args:
            user_id: Which account.

        Returns:
            The account, or ``None`` if there is no such account.
        """
        row = self._store.users.get(user_id)
        return self._hydrate(user_id, row) if row is not None else None

    async def find_by_email(self, email: str) -> User | None:
        """Look up an account by email address.

        Args:
            email: The address to find, in any capitalisation.

        Returns:
            The account, or ``None``.
        """
        user_id = self._store.email_index.get(normalize_email(email))
        return await self.get(user_id) if user_id else None

    async def find_by_username(self, username: str) -> User | None:
        """Look up an account by username.

        Args:
            username: The handle to find.

        Returns:
            The account, or ``None``.
        """
        user_id = self._store.username_index.get(username.strip().lower())
        return await self.get(user_id) if user_id else None

    async def update_settings(self, user_id: UUID, settings: UserSettings) -> UserSettings:
        """Replace a user's preferences.

        Args:
            user_id: Which account.
            settings: The complete new settings.

        Returns:
            The stored settings.

        Raises:
            KeyError: If the account does not exist.
        """
        self._store.users[user_id]["settings"] = settings.model_dump()
        return settings

    async def delete(self, user_id: UUID) -> datetime:
        """Delete an account and everything belonging to it.

        Args:
            user_id: Which account.

        Returns:
            When the deletion happened.

        Raises:
            KeyError: If the account does not exist.
        """
        row = self._store.users.pop(user_id)
        self._store.email_index.pop(row["email"], None)
        self._store.username_index.pop(row["username"].lower(), None)

        # In MySQL this happens through ON DELETE CASCADE. Here it is done by
        # hand, so both implementations leave the same state behind.
        for table in (
            self._store.campaigns,
            self._store.characters,
            self._store.sessions,
            self._store.messages,
        ):
            for key in [k for k, v in table.items() if v.get("user_id") == user_id]:
                del table[key]

        return datetime.now(UTC)


class MemoryCampaignRepository:
    """Campaigns."""

    def __init__(self, store: MemoryStore) -> None:
        """Set up the repository.

        Args:
            store: The shared in-memory tables.
        """
        self._store = store

    async def create(self, campaign: Campaign) -> Campaign:
        """Store a new campaign.

        Args:
            campaign: The campaign to store.

        Returns:
            The stored campaign.
        """
        self._store.campaigns[campaign.campaign_id] = {
            "user_id": campaign.user_id,
            "title": campaign.title,
            "premise": campaign.premise,
            "ruleset": campaign.ruleset,
            "tone": campaign.tone,
            "status": campaign.status,
            "created_at": campaign.created_at,
            "updated_at": campaign.updated_at,
        }
        return campaign

    @staticmethod
    def _hydrate(campaign_id: UUID, row: dict[str, Any]) -> Campaign:
        """Turn a stored row back into a domain object.

        Args:
            campaign_id: Which campaign.
            row: The stored row.

        Returns:
            The campaign.
        """
        return Campaign(
            campaign_id=campaign_id,
            user_id=row["user_id"],
            title=row["title"],
            premise=row["premise"],
            ruleset=row["ruleset"],
            tone=row["tone"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def get(self, user_id: UUID, campaign_id: UUID) -> Campaign | None:
        """Fetch one campaign, checking it belongs to the caller.

        Args:
            user_id: The owner. Checked, so guessing an identifier is not
                enough to read someone else's campaign.
            campaign_id: Which campaign.

        Returns:
            The campaign, or ``None``.
        """
        row = self._store.campaigns.get(campaign_id)
        if row is None or row["user_id"] != user_id:
            return None
        return self._hydrate(campaign_id, row)

    async def list_for_user(
        self, user_id: UUID, limit: int, offset: int
    ) -> tuple[list[Campaign], int]:
        """List a user's campaigns, most recently updated first.

        Args:
            user_id: The owner.
            limit: Page size.
            offset: How many to skip.

        Returns:
            The page of campaigns and the total count.
        """
        rows = [
            (cid, row)
            for cid, row in self._store.campaigns.items()
            if row["user_id"] == user_id and row["status"] != "deleted"
        ]
        rows.sort(key=lambda item: item[1]["updated_at"], reverse=True)
        page = rows[offset : offset + limit]
        return [self._hydrate(cid, row) for cid, row in page], len(rows)

    async def update(self, campaign: Campaign) -> Campaign:
        """Save changes to a campaign.

        Args:
            campaign: The campaign with its new values.

        Returns:
            The stored campaign.

        Raises:
            KeyError: If the campaign does not exist.
        """
        row = self._store.campaigns[campaign.campaign_id]
        row.update(
            {
                "title": campaign.title,
                "premise": campaign.premise,
                "tone": campaign.tone,
                "status": campaign.status,
                "updated_at": utc_now(),
            }
        )
        return replace(campaign, updated_at=row["updated_at"])

    async def delete(self, user_id: UUID, campaign_id: UUID) -> bool:
        """Remove a campaign and everything inside it.

        Args:
            user_id: The owner.
            campaign_id: Which campaign.

        Returns:
            True if something was removed.
        """
        row = self._store.campaigns.get(campaign_id)
        if row is None or row["user_id"] != user_id:
            return False
        del self._store.campaigns[campaign_id]
        for cid in [
            k for k, v in self._store.characters.items() if v["campaign_id"] == campaign_id
        ]:
            del self._store.characters[cid]
        return True


class MemoryCharacterRepository:
    """Player characters."""

    def __init__(self, store: MemoryStore) -> None:
        """Set up the repository.

        Args:
            store: The shared in-memory tables.
        """
        self._store = store

    async def create(self, character: Character) -> Character:
        """Store a new character.

        Args:
            character: The character to store.

        Returns:
            The stored character.
        """
        self._store.characters[character.character_id] = {
            "campaign_id": character.campaign_id,
            "user_id": character.user_id,
            "name": character.name,
            "sheet": character.sheet,
            "char_class": character.character_class,
            "char_level": character.level,
            "created_at": character.created_at,
            "updated_at": character.updated_at,
        }
        return character

    @staticmethod
    def _hydrate(character_id: UUID, row: dict[str, Any]) -> Character:
        """Turn a stored row back into a domain object.

        Args:
            character_id: Which character.
            row: The stored row.

        Returns:
            The character.
        """
        return Character(
            character_id=character_id,
            campaign_id=row["campaign_id"],
            user_id=row["user_id"],
            name=row["name"],
            character_class=row["char_class"],
            level=row["char_level"],
            sheet=row["sheet"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def get(self, user_id: UUID, character_id: UUID) -> Character | None:
        """Fetch one character belonging to the caller.

        Args:
            user_id: The owner.
            character_id: Which character.

        Returns:
            The character, or ``None``.
        """
        row = self._store.characters.get(character_id)
        if row is None or row["user_id"] != user_id:
            return None
        return self._hydrate(character_id, row)

    async def list_for_campaign(self, user_id: UUID, campaign_id: UUID) -> list[Character]:
        """List every character in one campaign.

        Args:
            user_id: The owner.
            campaign_id: Which campaign.

        Returns:
            The characters.
        """
        return [
            self._hydrate(cid, row)
            for cid, row in self._store.characters.items()
            if row["user_id"] == user_id and row["campaign_id"] == campaign_id
        ]

    async def update(self, character: Character) -> Character:
        """Save changes to a character.

        Args:
            character: The character with its new values.

        Returns:
            The stored character.

        Raises:
            KeyError: If the character does not exist.
        """
        row = self._store.characters[character.character_id]
        row.update(
            {
                "name": character.name,
                "sheet": character.sheet,
                "char_level": character.level,
                "updated_at": utc_now(),
            }
        )
        return replace(character, updated_at=row["updated_at"])

    async def delete(self, user_id: UUID, character_id: UUID) -> bool:
        """Remove a character.

        Args:
            user_id: The owner.
            character_id: Which character.

        Returns:
            True if something was removed.
        """
        row = self._store.characters.get(character_id)
        if row is None or row["user_id"] != user_id:
            return False
        del self._store.characters[character_id]
        return True


class MemorySessionRepository:
    """Play sessions and their transcripts."""

    def __init__(self, store: MemoryStore) -> None:
        """Set up the repository.

        Args:
            store: The shared in-memory tables.
        """
        self._store = store

    async def create_session(self, session: GameSession) -> GameSession:
        """Start a new play session.

        Args:
            session: The session to store.

        Returns:
            The stored session.
        """
        self._store.sessions[session.game_session_id] = {
            "campaign_id": session.campaign_id,
            "user_id": session.user_id,
            "started_at": session.started_at,
            "ended_at": None,
            "turn_count": 0,
        }
        return session

    async def get_session(self, user_id: UUID, session_id: UUID) -> GameSession | None:
        """Fetch one session belonging to the caller.

        Args:
            user_id: The owner.
            session_id: Which session.

        Returns:
            The session, or ``None``.
        """
        row = self._store.sessions.get(session_id)
        if row is None or row["user_id"] != user_id:
            return None
        return GameSession(
            game_session_id=session_id,
            campaign_id=row["campaign_id"],
            user_id=row["user_id"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            turn_count=row["turn_count"],
        )

    async def append_message(self, message: Message) -> Message:
        """Add a message to a transcript, assigning its position.

        The sequence number is assigned under a lock. Without it, two requests
        arriving together could both read "the last message was number 6" and
        both write number 7, losing one of them.

        Args:
            message: The message to store.

        Returns:
            The stored message with its sequence number set.
        """
        async with self._store.lock:
            existing = [
                row
                for row in self._store.messages.values()
                if row["game_session_id"] == message.game_session_id
            ]
            seq = max((row["seq"] for row in existing), default=0) + 1
            self._store.messages[message.message_id] = {
                "game_session_id": message.game_session_id,
                "user_id": message.user_id,
                "seq": seq,
                "role": message.role,
                "content": message.content,
                "input_mode": message.input_mode,
                "token_count": message.token_count,
                "created_at": message.created_at,
            }
            session = self._store.sessions.get(message.game_session_id)
            if session is not None and message.role == "player":
                session["turn_count"] += 1
        return replace(message, seq=seq)

    async def list_messages(
        self, user_id: UUID, session_id: UUID, after_seq: int, limit: int
    ) -> list[Message]:
        """Read a page of a transcript.

        Args:
            user_id: The owner.
            session_id: Which session.
            after_seq: Return messages after this position.
            limit: Page size.

        Returns:
            The messages, in order.
        """
        rows = [
            (mid, row)
            for mid, row in self._store.messages.items()
            if row["game_session_id"] == session_id
            and row["user_id"] == user_id
            and row["seq"] > after_seq
        ]
        rows.sort(key=lambda item: item[1]["seq"])
        return [
            Message(
                message_id=mid,
                game_session_id=session_id,
                user_id=user_id,
                seq=row["seq"],
                role=row["role"],
                content=row["content"],
                input_mode=row["input_mode"],
                token_count=row["token_count"],
                created_at=row["created_at"],
            )
            for mid, row in rows[:limit]
        ]


def new_id() -> UUID:
    """Create a random identifier.

    Returns:
        A random UUID version 4. Random rather than sequential, so identifiers
        reveal nothing about how many accounts exist or in what order they were
        created — both of which a counting identifier would leak, and both of
        which would let someone enumerate other people's records by guessing.
    """
    return uuid4()
