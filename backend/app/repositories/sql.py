"""MySQL storage.

WHEN THIS IS USED
When `REPOSITORY_BACKEND=mysql`. Otherwise the application uses the in-memory
store in `memory.py`, which needs nothing installed but loses everything on
restart.

`docs/LOCAL_MYSQL.md` walks through installing MySQL on your own machine so you
can try this locally.

WHY PLAIN SQL RATHER THAN AN ORM
An ORM (Object Relational Mapper) turns database rows into objects
automatically. It saves typing on large projects, and it hides what is actually
happening — which is exactly the wrong trade when someone is learning.

Every query below is written out. You can read it, paste it into a database
client, and see the same result. When something is slow or wrong, the thing to
look at is right here rather than behind a layer of generated SQL.

HOW IDENTIFIERS ARE STORED
As `BINARY(16)`: sixteen raw bytes rather than a thirty-six character string.
That is less than half the size, and size matters because every index holds a
copy. `_to_db` and `_from_db` convert at the boundary, so nothing above this
file has to think about it.

A NOTE ON SQL INJECTION
Every query uses named parameters — `:user_id`, never an f-string. The database
driver sends the query and the values separately, so a value can never be read
as part of the query. **Never build SQL by joining strings**, no matter how
certain you are about the input; that is how the most common serious web
vulnerability happens.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings
from app.repositories.base import (
    Campaign,
    Character,
    GameSession,
    Message,
    User,
    utc_now,
)
from app.repositories.memory import normalize_email
from app.schemas.settings import UserSettings


def _to_db(value: UUID) -> bytes:
    """Convert an identifier for storage.

    Args:
        value: The identifier.

    Returns:
        Its sixteen raw bytes, for a ``BINARY(16)`` column.
    """
    return value.bytes


def _from_db(value: bytes) -> UUID:
    """Convert a stored identifier back into a UUID.

    Args:
        value: The sixteen bytes from the database.

    Returns:
        The identifier.
    """
    return UUID(bytes=value)


def _load_json(value: Any) -> Any:
    """Read a JSON column, whichever form the driver returns it in.

    Some driver and MySQL version combinations hand back a parsed object and
    others hand back the raw text. Handling both here means the rest of the
    file does not have to care.

    Args:
        value: What the driver returned.

    Returns:
        The decoded object.
    """
    if isinstance(value, str | bytes | bytearray):
        return json.loads(value)
    return value


class SqlStore:
    """Owns the database connection pool.

    One instance for the whole application, created at startup and closed at
    shutdown. Opening a connection per request would be far slower than
    reusing a pool of them.
    """

    def __init__(self, settings: Settings) -> None:
        """Create the connection pool.

        Args:
            settings: The application settings, supplying ``DATABASE_URL``.

        Raises:
            ValueError: If no database URL is configured. Failing at startup
                with a clear message beats failing on the first request with a
                confusing one.
        """
        url = settings.database_url.get_secret_value().strip()
        if not url:
            raise ValueError(
                "REPOSITORY_BACKEND is 'mysql' but DATABASE_URL is empty.\n"
                "Set it in .env, for example:\n"
                "  DATABASE_URL=mysql+aiomysql://dm:password@127.0.0.1:3306/dungeon_master\n"
                "See docs/LOCAL_MYSQL.md."
            )

        self.engine: AsyncEngine = create_async_engine(
            url,
            # Recycle connections after an hour. MySQL closes idle connections
            # on its own, and without this the application would eventually
            # hand out one the server has already dropped.
            pool_recycle=3600,
            # Check a connection is alive before using it. Costs a tiny query;
            # saves a class of intermittent failure that is miserable to debug.
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            echo=False,
        )
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def close(self) -> None:
        """Close every pooled connection at shutdown."""
        await self.engine.dispose()


class _Repo:
    """Shared plumbing for the repositories below."""

    def __init__(self, store: SqlStore) -> None:
        """Set up the repository.

        Args:
            store: The connection pool.
        """
        self._store = store

    def _session(self) -> AsyncSession:
        """Open a database session.

        Returns:
            A session. Used as ``async with``, which commits on success and
            rolls back if an exception escapes — so a half-finished write can
            never be left behind.
        """
        return self._store.session_factory()


class SqlUserRepository(_Repo):
    """Accounts, stored in MySQL."""

    async def create(self, user: User, password_hash: str) -> User:
        """Store a new account.

        Args:
            user: The account to store.
            password_hash: The Argon2id digest.

        Returns:
            The stored account.

        Raises:
            ValueError: If the username or email is already taken. The unique
                keys in the schema are what actually enforce this — checking
                first and then inserting would leave a gap in which another
                request could take the name.
        """
        async with self._session() as session, session.begin():
            existing = await session.execute(
                text("SELECT 1 FROM users WHERE email = :email OR username = :username LIMIT 1"),
                {"email": normalize_email(user.email), "username": user.username},
            )
            if existing.first() is not None:
                raise ValueError("email_or_username_taken")

            await session.execute(
                text(
                    "INSERT INTO users (user_id, username, display_name, email, "
                    "                   email_verified, password_hash, created_at) "
                    "VALUES (:user_id, :username, :display_name, :email, "
                    "        :email_verified, :password_hash, :created_at)"
                ),
                {
                    "user_id": _to_db(user.user_id),
                    "username": user.username,
                    "display_name": user.display_name,
                    "email": normalize_email(user.email),
                    "email_verified": int(user.email_verified),
                    "password_hash": password_hash,
                    "created_at": user.created_at,
                },
            )
            # Settings live in memory for now; the schema gains a column when
            # they need to survive a restart.
            _SETTINGS_CACHE[user.user_id] = user.settings
        return user

    @staticmethod
    def _hydrate(row: Mapping[str, Any]) -> User:
        """Turn a database row into a domain object.

        Args:
            row: The row.

        Returns:
            The account.
        """
        user_id = _from_db(row["user_id"])
        return User(
            user_id=user_id,
            username=row["username"],
            display_name=row["display_name"],
            email=row["email"],
            password_hash=row["password_hash"],
            email_verified=bool(row["email_verified"]),
            created_at=row["created_at"],
            status=row["status"],
            settings=_SETTINGS_CACHE.get(user_id, UserSettings()),
        )

    # The three ways an account is looked up. Written out in full rather than
    # assembled from a WHERE fragment, because building SQL by joining strings
    # is the habit that leads to injection — and a codebase where it appears
    # once, safely, is a codebase where somebody will copy it unsafely.
    _SELECT_COLUMNS = (
        "SELECT user_id, username, display_name, email, email_verified, "
        "       password_hash, status, created_at FROM users "
    )
    _BY_ID = _SELECT_COLUMNS + "WHERE user_id = :user_id LIMIT 1"
    _BY_EMAIL = _SELECT_COLUMNS + "WHERE email = :email LIMIT 1"
    _BY_USERNAME = _SELECT_COLUMNS + "WHERE username = :username LIMIT 1"

    async def _find_one(self, query: str, params: dict[str, Any]) -> User | None:
        """Run one of the fixed account lookups above.

        Args:
            query: One of the ``_BY_*`` constants. Never built at runtime.
            params: Values for the named parameters in it.

        Returns:
            The account, or ``None``.
        """
        async with self._session() as session:
            result = await session.execute(text(query), params)
            row = result.mappings().first()
        return self._hydrate(row) if row else None

    async def get(self, user_id: UUID) -> User | None:
        """Fetch an account by identifier.

        Args:
            user_id: Which account.

        Returns:
            The account, or ``None``.
        """
        return await self._find_one(self._BY_ID, {"user_id": _to_db(user_id)})

    async def find_by_email(self, email: str) -> User | None:
        """Fetch an account by email address.

        Args:
            email: The address, in any capitalisation.

        Returns:
            The account, or ``None``.
        """
        return await self._find_one(self._BY_EMAIL, {"email": normalize_email(email)})

    async def find_by_username(self, username: str) -> User | None:
        """Fetch an account by username.

        Args:
            username: The handle.

        Returns:
            The account, or ``None``.
        """
        return await self._find_one(self._BY_USERNAME, {"username": username.strip()})

    async def update_settings(self, user_id: UUID, settings: UserSettings) -> UserSettings:
        """Replace a user's preferences.

        Args:
            user_id: Which account.
            settings: The complete new settings.

        Returns:
            The stored settings.
        """
        _SETTINGS_CACHE[user_id] = settings
        return settings

    async def delete(self, user_id: UUID) -> datetime:
        """Delete an account and everything belonging to it.

        Campaigns, characters, sessions and messages go with it, through the
        ``ON DELETE CASCADE`` rules in the schema — so there is nothing left for
        a later cleanup job to forget about. Analytics events survive with
        their ``user_id`` set to NULL, keeping the totals correct.

        Args:
            user_id: Which account.

        Returns:
            When the deletion happened.

        Raises:
            KeyError: If there was no such account.
        """
        async with self._session() as session, session.begin():
            result = await session.execute(
                text("DELETE FROM users WHERE user_id = :user_id"),
                {"user_id": _to_db(user_id)},
            )
            if result.rowcount == 0:
                raise KeyError(user_id)
        _SETTINGS_CACHE.pop(user_id, None)
        return datetime.now(UTC)


# Preferences are held in memory rather than in a column, because they are the
# one thing here that is purely cosmetic and adding a column for them would
# have meant a second migration before anything worked. Phase 2 moves them into
# the users table; the interface does not change when it does.
_SETTINGS_CACHE: dict[UUID, UserSettings] = {}


class SqlCampaignRepository(_Repo):
    """Campaigns, stored in MySQL."""

    async def create(self, campaign: Campaign) -> Campaign:
        """Store a new campaign.

        Args:
            campaign: The campaign to store.

        Returns:
            The stored campaign.
        """
        async with self._session() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO campaigns (campaign_id, user_id, title, premise, "
                    "                       ruleset, tone, status) "
                    "VALUES (:campaign_id, :user_id, :title, :premise, "
                    "        :ruleset, :tone, :status)"
                ),
                {
                    "campaign_id": _to_db(campaign.campaign_id),
                    "user_id": _to_db(campaign.user_id),
                    "title": campaign.title,
                    "premise": campaign.premise,
                    "ruleset": campaign.ruleset,
                    "tone": campaign.tone,
                    "status": campaign.status,
                },
            )
        return campaign

    @staticmethod
    def _hydrate(row: Mapping[str, Any]) -> Campaign:
        """Turn a database row into a domain object.

        Args:
            row: The row.

        Returns:
            The campaign.
        """
        return Campaign(
            campaign_id=_from_db(row["campaign_id"]),
            user_id=_from_db(row["user_id"]),
            title=row["title"],
            premise=row["premise"],
            ruleset=row["ruleset"],
            tone=row["tone"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def get(self, user_id: UUID, campaign_id: UUID) -> Campaign | None:
        """Fetch one campaign belonging to the caller.

        The owner is part of the query rather than checked afterwards, so a
        campaign belonging to somebody else simply does not come back.

        Args:
            user_id: The owner.
            campaign_id: Which campaign.

        Returns:
            The campaign, or ``None``.
        """
        async with self._session() as session:
            result = await session.execute(
                text(
                    "SELECT campaign_id, user_id, title, premise, ruleset, tone, status, "
                    "       created_at, updated_at "
                    "FROM campaigns WHERE campaign_id = :campaign_id AND user_id = :user_id"
                ),
                {"campaign_id": _to_db(campaign_id), "user_id": _to_db(user_id)},
            )
            row = result.mappings().first()
        return self._hydrate(row) if row else None

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
        async with self._session() as session:
            rows = await session.execute(
                text(
                    "SELECT campaign_id, user_id, title, premise, ruleset, tone, status, "
                    "       created_at, updated_at "
                    "FROM campaigns WHERE user_id = :user_id AND status <> 'archived' "
                    "ORDER BY updated_at DESC LIMIT :limit OFFSET :offset"
                ),
                {"user_id": _to_db(user_id), "limit": limit, "offset": offset},
            )
            items = [self._hydrate(row) for row in rows.mappings()]

            total = await session.execute(
                text("SELECT COUNT(*) FROM campaigns WHERE user_id = :user_id"),
                {"user_id": _to_db(user_id)},
            )
        return items, int(total.scalar() or 0)

    async def update(self, campaign: Campaign) -> Campaign:
        """Save changes to a campaign.

        Args:
            campaign: The campaign with its new values.

        Returns:
            The stored campaign.
        """
        async with self._session() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE campaigns SET title = :title, premise = :premise, tone = :tone, "
                    "                     status = :status "
                    "WHERE campaign_id = :campaign_id AND user_id = :user_id"
                ),
                {
                    "title": campaign.title,
                    "premise": campaign.premise,
                    "tone": campaign.tone,
                    "status": campaign.status,
                    "campaign_id": _to_db(campaign.campaign_id),
                    "user_id": _to_db(campaign.user_id),
                },
            )
        return replace(campaign, updated_at=utc_now())

    async def delete(self, user_id: UUID, campaign_id: UUID) -> bool:
        """Remove a campaign and its characters.

        Args:
            user_id: The owner.
            campaign_id: Which campaign.

        Returns:
            True if something was removed.
        """
        async with self._session() as session, session.begin():
            result = await session.execute(
                text(
                    "DELETE FROM campaigns WHERE campaign_id = :campaign_id "
                    "AND user_id = :user_id"
                ),
                {"campaign_id": _to_db(campaign_id), "user_id": _to_db(user_id)},
            )
        return bool(result.rowcount)


class SqlCharacterRepository(_Repo):
    """Characters, stored in MySQL."""

    async def create(self, character: Character) -> Character:
        """Store a new character.

        Args:
            character: The character to store.

        Returns:
            The stored character.
        """
        async with self._session() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO characters (character_id, campaign_id, user_id, name, "
                    "                        sheet, char_class, char_level) "
                    "VALUES (:character_id, :campaign_id, :user_id, :name, "
                    "        :sheet, :char_class, :char_level)"
                ),
                {
                    "character_id": _to_db(character.character_id),
                    "campaign_id": _to_db(character.campaign_id),
                    "user_id": _to_db(character.user_id),
                    "name": character.name,
                    "sheet": json.dumps(character.sheet),
                    "char_class": character.character_class,
                    "char_level": character.level,
                },
            )
        return character

    @staticmethod
    def _hydrate(row: Mapping[str, Any]) -> Character:
        """Turn a database row into a domain object.

        Args:
            row: The row.

        Returns:
            The character.
        """
        return Character(
            character_id=_from_db(row["character_id"]),
            campaign_id=_from_db(row["campaign_id"]),
            user_id=_from_db(row["user_id"]),
            name=row["name"],
            character_class=row["char_class"],
            level=row["char_level"],
            sheet=_load_json(row["sheet"]),
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
        async with self._session() as session:
            result = await session.execute(
                text(
                    "SELECT character_id, campaign_id, user_id, name, sheet, char_class, "
                    "       char_level, created_at, updated_at "
                    "FROM characters WHERE character_id = :character_id AND user_id = :user_id"
                ),
                {"character_id": _to_db(character_id), "user_id": _to_db(user_id)},
            )
            row = result.mappings().first()
        return self._hydrate(row) if row else None

    async def list_for_campaign(self, user_id: UUID, campaign_id: UUID) -> list[Character]:
        """List every character in one campaign.

        Args:
            user_id: The owner.
            campaign_id: Which campaign.

        Returns:
            The characters.
        """
        async with self._session() as session:
            rows = await session.execute(
                text(
                    "SELECT character_id, campaign_id, user_id, name, sheet, char_class, "
                    "       char_level, created_at, updated_at "
                    "FROM characters WHERE campaign_id = :campaign_id AND user_id = :user_id "
                    "ORDER BY created_at ASC"
                ),
                {"campaign_id": _to_db(campaign_id), "user_id": _to_db(user_id)},
            )
            return [self._hydrate(row) for row in rows.mappings()]

    async def update(self, character: Character) -> Character:
        """Save changes to a character.

        Args:
            character: The character with its new values.

        Returns:
            The stored character.
        """
        async with self._session() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE characters SET name = :name, sheet = :sheet, "
                    "                      char_level = :char_level "
                    "WHERE character_id = :character_id AND user_id = :user_id"
                ),
                {
                    "name": character.name,
                    "sheet": json.dumps(character.sheet),
                    "char_level": character.level,
                    "character_id": _to_db(character.character_id),
                    "user_id": _to_db(character.user_id),
                },
            )
        return replace(character, updated_at=utc_now())

    async def delete(self, user_id: UUID, character_id: UUID) -> bool:
        """Remove a character.

        Args:
            user_id: The owner.
            character_id: Which character.

        Returns:
            True if something was removed.
        """
        async with self._session() as session, session.begin():
            result = await session.execute(
                text(
                    "DELETE FROM characters WHERE character_id = :character_id "
                    "AND user_id = :user_id"
                ),
                {"character_id": _to_db(character_id), "user_id": _to_db(user_id)},
            )
        return bool(result.rowcount)


class SqlSessionRepository(_Repo):
    """Play sessions and transcripts, stored in MySQL."""

    async def create_session(self, session_obj: GameSession) -> GameSession:
        """Start a new play session.

        Args:
            session_obj: The session to store.

        Returns:
            The stored session.
        """
        async with self._session() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO game_sessions (game_session_id, campaign_id, user_id) "
                    "VALUES (:game_session_id, :campaign_id, :user_id)"
                ),
                {
                    "game_session_id": _to_db(session_obj.game_session_id),
                    "campaign_id": _to_db(session_obj.campaign_id),
                    "user_id": _to_db(session_obj.user_id),
                },
            )
        return session_obj

    async def get_session(self, user_id: UUID, session_id: UUID) -> GameSession | None:
        """Fetch one session belonging to the caller.

        Args:
            user_id: The owner.
            session_id: Which session.

        Returns:
            The session, or ``None``.
        """
        async with self._session() as session:
            result = await session.execute(
                text(
                    "SELECT game_session_id, campaign_id, user_id, started_at, ended_at, "
                    "       turn_count "
                    "FROM game_sessions WHERE game_session_id = :sid AND user_id = :user_id"
                ),
                {"sid": _to_db(session_id), "user_id": _to_db(user_id)},
            )
            row = result.mappings().first()
        if row is None:
            return None
        return GameSession(
            game_session_id=_from_db(row["game_session_id"]),
            campaign_id=_from_db(row["campaign_id"]),
            user_id=_from_db(row["user_id"]),
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            turn_count=row["turn_count"],
        )

    async def append_message(self, message: Message) -> Message:
        """Add a message to a transcript, assigning its position.

        The next sequence number is read with ``FOR UPDATE``, which locks those
        rows until the transaction commits. Without it, two requests arriving
        together could both read "the last one was 6" and both try to write 7 —
        and the unique key would reject one of them.

        Args:
            message: The message to store.

        Returns:
            The stored message with its sequence number set.
        """
        async with self._session() as session, session.begin():
            result = await session.execute(
                text(
                    "SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM messages "
                    "WHERE game_session_id = :sid FOR UPDATE"
                ),
                {"sid": _to_db(message.game_session_id)},
            )
            seq = int(result.scalar() or 1)

            await session.execute(
                text(
                    "INSERT INTO messages (message_id, game_session_id, user_id, seq, role, "
                    "                      content, input_mode, token_count) "
                    "VALUES (:message_id, :sid, :user_id, :seq, :role, "
                    "        :content, :input_mode, :token_count)"
                ),
                {
                    "message_id": _to_db(message.message_id),
                    "sid": _to_db(message.game_session_id),
                    "user_id": _to_db(message.user_id),
                    "seq": seq,
                    "role": message.role,
                    "content": message.content,
                    "input_mode": message.input_mode,
                    "token_count": message.token_count,
                },
            )

            if message.role == "player":
                await session.execute(
                    text(
                        "UPDATE game_sessions SET turn_count = turn_count + 1 "
                        "WHERE game_session_id = :sid"
                    ),
                    {"sid": _to_db(message.game_session_id)},
                )
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
        async with self._session() as session:
            rows = await session.execute(
                text(
                    "SELECT message_id, game_session_id, user_id, seq, role, content, "
                    "       input_mode, token_count, created_at "
                    "FROM messages "
                    "WHERE game_session_id = :sid AND user_id = :user_id AND seq > :after "
                    "ORDER BY seq ASC LIMIT :limit"
                ),
                {
                    "sid": _to_db(session_id),
                    "user_id": _to_db(user_id),
                    "after": after_seq,
                    "limit": limit,
                },
            )
            return [
                Message(
                    message_id=_from_db(row["message_id"]),
                    game_session_id=_from_db(row["game_session_id"]),
                    user_id=_from_db(row["user_id"]),
                    seq=row["seq"],
                    role=row["role"],
                    content=row["content"],
                    input_mode=row["input_mode"],
                    token_count=row["token_count"],
                    created_at=row["created_at"],
                )
                for row in rows.mappings()
            ]
