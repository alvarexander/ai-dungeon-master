"""In-memory storage for Phase 1, encrypting exactly as the database will.

WHY THIS IS NOT A TOY
It would have been easier to store plain Python objects in a dictionary and add
encryption later. That was rejected deliberately. This implementation runs the
real encryption code on every write and the real decryption code on every read,
against the local development key. The result is that the encryption path is
exercised from the first day rather than being a diagram that gets tested for
the first time on deployment day.

What is genuinely temporary is only *where the bytes land*: a dictionary in this
process instead of MySQL. Everything above this file — services, endpoints —
will not change when the database arrives.

WHAT "RESTART LOSES EVERYTHING" MEANS FOR YOU
There is no file and no database. Stop the server and every campaign, character
and transcript is gone. That is expected in Phase 1 and is why the seed script
exists: run it to get a populated demo account back in one command.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.core.security.blind_index import BlindIndexService
from app.core.security.crypto import EncryptionService, FieldRef, WrappedKey
from app.repositories.base import (
    Campaign,
    Character,
    GameSession,
    Message,
    User,
    utc_now,
)
from app.schemas.settings import UserSettings

# The columns this store encrypts, named exactly as they are in the SQL schema
# so that the binding between ciphertext and its location matches what the
# database will use. Change one and the other must change with it.
F_EMAIL = FieldRef("users", "email")
F_CAMPAIGN_TITLE = FieldRef("campaigns", "title")
F_CAMPAIGN_PREMISE = FieldRef("campaigns", "premise")
F_CHARACTER_NAME = FieldRef("characters", "name")
F_CHARACTER_SHEET = FieldRef("characters", "sheet")
F_MESSAGE_CONTENT = FieldRef("messages", "content")


class MemoryStore:
    """The shared in-memory tables. One instance for the whole application.

    Holds ciphertext, exactly as MySQL would. If you inspect this object in a
    debugger you will see byte strings, not email addresses — which is the
    point, and a useful way to convince yourself the encryption is real.
    """

    def __init__(self) -> None:
        """Create empty tables."""
        self.users: dict[UUID, dict[str, Any]] = {}
        self.email_bidx_index: dict[bytes, UUID] = {}
        self.username_index: dict[str, UUID] = {}
        self.campaigns: dict[UUID, dict[str, Any]] = {}
        self.characters: dict[UUID, dict[str, Any]] = {}
        self.sessions: dict[UUID, dict[str, Any]] = {}
        self.messages: dict[UUID, dict[str, Any]] = {}
        # Guards the sequence-number assignment, which is the one place two
        # concurrent requests could otherwise collide.
        self.lock = asyncio.Lock()

    def clear(self) -> None:
        """Empty every table. Used by tests and by the seed script."""
        self.users.clear()
        self.email_bidx_index.clear()
        self.username_index.clear()
        self.campaigns.clear()
        self.characters.clear()
        self.sessions.clear()
        self.messages.clear()


class MemoryUserRepository:
    """Accounts, with personal fields encrypted at this boundary."""

    def __init__(
        self, store: MemoryStore, encryption: EncryptionService, blind_index: BlindIndexService
    ) -> None:
        """Set up the repository.

        Args:
            store: The shared in-memory tables.
            encryption: Turns plaintext into ciphertext and back.
            blind_index: Produces the searchable email fingerprint.
        """
        self._store = store
        self._encryption = encryption
        self._blind_index = blind_index

    async def create(self, user: User, password_hash: str) -> User:
        """Store a new account, minting an encryption key for it.

        Every new account gets its own Data Encryption Key here. That is what
        makes deletion possible later: destroy this one key and everything the
        account ever writes becomes unreadable.

        Args:
            user: The account to store, with plaintext fields.
            password_hash: The Argon2id digest of their password.

        Returns:
            The stored account.

        Raises:
            ValueError: If the username or email is already taken.
        """
        email_bidx = self._blind_index.email_index(user.email)
        if email_bidx in self._store.email_bidx_index:
            raise ValueError("email_taken")
        if user.username.lower() in self._store.username_index:
            raise ValueError("username_taken")

        wrapped, cipher = self._encryption.create_user_key(user.user_id)

        self._store.users[user.user_id] = {
            # Plaintext by classification.
            "username": user.username,
            "display_name": user.display_name,
            "email_verified": user.email_verified,
            "created_at": user.created_at,
            "status": "active",
            "settings": user.settings.model_dump(),
            # Hashed — one way, never reversible.
            "password_hash": password_hash,
            # Blind index — searchable fingerprint, not reversible.
            "email_bidx": email_bidx,
            # Encrypted — this is ciphertext from here on.
            "email_ct": cipher.encrypt(F_EMAIL, user.email),
            # The wrapped key. Setting this to None is account deletion.
            "dek": wrapped,
        }
        self._store.email_bidx_index[email_bidx] = user.user_id
        self._store.username_index[user.username.lower()] = user.user_id
        return user

    def _hydrate(self, user_id: UUID, row: dict[str, Any]) -> User:
        """Turn a stored row back into a domain object, decrypting as it goes.

        Args:
            user_id: Which account the row belongs to.
            row: The stored row.

        Returns:
            The account with plaintext fields.

        Raises:
            CryptoShreddedError: If the account has been deleted, in which case
                its data is permanently unreadable.
        """
        cipher = self._encryption.cipher_for(user_id, row["dek"])
        return User(
            user_id=user_id,
            username=row["username"],
            display_name=row["display_name"],
            email=cipher.decrypt(F_EMAIL, row["email_ct"]),
            password_hash=row["password_hash"],
            email_verified=row["email_verified"],
            created_at=row["created_at"],
            status=row["status"],
            settings=UserSettings(**row["settings"]),
        )

    async def get(self, user_id: UUID) -> User | None:
        """Fetch an account and decrypt its fields.

        Args:
            user_id: Which account.

        Returns:
            The account, or ``None`` if there is no such account or it has been
            shredded.
        """
        row = self._store.users.get(user_id)
        if row is None or row["dek"] is None:
            return None
        return self._hydrate(user_id, row)

    async def find_by_email(self, email: str) -> User | None:
        """Look up an account by email address, without comparing addresses.

        The address is turned into a fingerprint first. The stored ciphertext
        is never compared — it could not be, since encrypting the same address
        twice produces different bytes.

        Args:
            email: The address to find.

        Returns:
            The account, or ``None``.
        """
        user_id = self._store.email_bidx_index.get(self._blind_index.email_index(email))
        return await self.get(user_id) if user_id else None

    async def find_by_username(self, username: str) -> User | None:
        """Look up an account by its plaintext username.

        Args:
            username: The handle to find.

        Returns:
            The account, or ``None``.
        """
        user_id = self._store.username_index.get(username.strip().lower())
        return await self.get(user_id) if user_id else None

    async def update_settings(self, user_id: UUID, settings: UserSettings) -> UserSettings:
        """Replace a user's preferences.

        Settings are enumerated values and booleans, so they are stored in
        plaintext and this needs no key at all.

        Args:
            user_id: Which account.
            settings: The complete new settings.

        Returns:
            The stored settings.

        Raises:
            KeyError: If the account does not exist.
        """
        row = self._store.users[user_id]
        row["settings"] = settings.model_dump()
        return settings

    async def crypto_shred(self, user_id: UUID) -> datetime:
        """Delete an account by destroying its encryption key.

        Look at what this method does not do. It never touches the campaigns,
        the characters, or the transcripts. It removes one small field — the
        wrapped key — and at that instant every encrypted byte belonging to
        this account becomes permanently undecryptable, here and in any backup
        that was ever taken.

        Args:
            user_id: Which account.

        Returns:
            When the key was destroyed.

        Raises:
            KeyError: If the account does not exist.
        """
        row = self._store.users[user_id]
        row["dek"] = None
        row["status"] = "shredded"
        # Remove the lookup entries so the account cannot be found again.
        self._store.email_bidx_index.pop(row["email_bidx"], None)
        self._store.username_index.pop(row["username"].lower(), None)
        # Drop the cached key, so a decryption cannot succeed for the next few
        # minutes on the strength of a cache entry.
        self._encryption.forget(user_id)
        return datetime.now(UTC)

    def _cipher(self, user_id: UUID) -> Any:
        """Get the cipher for a user, for use by the sibling repositories.

        Args:
            user_id: Whose key is needed.

        Returns:
            A cipher scoped to that user.

        Raises:
            KeyError: If the account does not exist.
        """
        row = self._store.users[user_id]
        return self._encryption.cipher_for(user_id, row["dek"])


class MemoryCampaignRepository:
    """Campaigns, with the title and premise encrypted."""

    def __init__(self, store: MemoryStore, users: MemoryUserRepository) -> None:
        """Set up the repository.

        Args:
            store: The shared in-memory tables.
            users: Used to obtain the owning user's cipher. Campaign data is
                encrypted under the *owner's* key, which is what makes deleting
                the owner destroy their campaigns too.
        """
        self._store = store
        self._users = users

    async def create(self, campaign: Campaign) -> Campaign:
        """Store a new campaign, encrypting its free-text fields.

        Args:
            campaign: The campaign to store.

        Returns:
            The stored campaign.
        """
        cipher = self._users._cipher(campaign.user_id)  # noqa: SLF001 - same layer
        self._store.campaigns[campaign.campaign_id] = {
            "user_id": campaign.user_id,
            "title_ct": cipher.encrypt(F_CAMPAIGN_TITLE, campaign.title),
            "premise_ct": (
                cipher.encrypt(F_CAMPAIGN_PREMISE, campaign.premise) if campaign.premise else None
            ),
            "ruleset": campaign.ruleset,
            "tone": campaign.tone,
            "status": campaign.status,
            "created_at": campaign.created_at,
            "updated_at": campaign.updated_at,
        }
        return campaign

    def _hydrate(self, campaign_id: UUID, row: dict[str, Any]) -> Campaign:
        """Decrypt a stored campaign row.

        Args:
            campaign_id: Which campaign.
            row: The stored row.

        Returns:
            The campaign with plaintext fields.
        """
        cipher = self._users._cipher(row["user_id"])  # noqa: SLF001
        return Campaign(
            campaign_id=campaign_id,
            user_id=row["user_id"],
            title=cipher.decrypt(F_CAMPAIGN_TITLE, row["title_ct"]),
            premise=(
                cipher.decrypt(F_CAMPAIGN_PREMISE, row["premise_ct"]) if row["premise_ct"] else None
            ),
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

        Ordering is by timestamp rather than title, because titles are
        ciphertext and cannot be sorted before decryption. This is the concrete
        everyday cost of encrypting free text, and it is why pages are capped.

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
        """Save changes to a campaign, re-encrypting the text fields.

        Args:
            campaign: The campaign with its new values.

        Returns:
            The stored campaign.

        Raises:
            KeyError: If the campaign does not exist.
        """
        cipher = self._users._cipher(campaign.user_id)  # noqa: SLF001
        row = self._store.campaigns[campaign.campaign_id]
        row.update(
            {
                "title_ct": cipher.encrypt(F_CAMPAIGN_TITLE, campaign.title),
                "premise_ct": (
                    cipher.encrypt(F_CAMPAIGN_PREMISE, campaign.premise)
                    if campaign.premise
                    else None
                ),
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
    """Characters, with the name and sheet encrypted and the class in plaintext."""

    def __init__(self, store: MemoryStore, users: MemoryUserRepository) -> None:
        """Set up the repository.

        Args:
            store: The shared in-memory tables.
            users: Source of the owning user's cipher.
        """
        self._store = store
        self._users = users

    async def create(self, character: Character) -> Character:
        """Store a new character.

        Note the split: ``name`` and ``sheet`` are encrypted because a player
        may put a real person's name in either. ``character_class`` and
        ``level`` are plaintext because "level 4 rogue" identifies nobody, and
        keeping them readable means aggregate questions need no decryption.

        Args:
            character: The character to store.

        Returns:
            The stored character.
        """
        cipher = self._users._cipher(character.user_id)  # noqa: SLF001
        self._store.characters[character.character_id] = {
            "campaign_id": character.campaign_id,
            "user_id": character.user_id,
            "name_ct": cipher.encrypt(F_CHARACTER_NAME, character.name),
            "sheet_ct": cipher.encrypt_json(F_CHARACTER_SHEET, character.sheet),
            "char_class": character.character_class,
            "char_level": character.level,
            "created_at": character.created_at,
            "updated_at": character.updated_at,
        }
        return character

    def _hydrate(self, character_id: UUID, row: dict[str, Any]) -> Character:
        """Decrypt a stored character row.

        Args:
            character_id: Which character.
            row: The stored row.

        Returns:
            The character with plaintext fields.
        """
        cipher = self._users._cipher(row["user_id"])  # noqa: SLF001
        return Character(
            character_id=character_id,
            campaign_id=row["campaign_id"],
            user_id=row["user_id"],
            name=cipher.decrypt(F_CHARACTER_NAME, row["name_ct"]),
            character_class=row["char_class"],
            level=row["char_level"],
            sheet=cipher.decrypt_json(F_CHARACTER_SHEET, row["sheet_ct"]),
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
        cipher = self._users._cipher(character.user_id)  # noqa: SLF001
        row = self._store.characters[character.character_id]
        row.update(
            {
                "name_ct": cipher.encrypt(F_CHARACTER_NAME, character.name),
                "sheet_ct": cipher.encrypt_json(F_CHARACTER_SHEET, character.sheet),
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
    """Play sessions and transcripts, with message content encrypted."""

    def __init__(self, store: MemoryStore, users: MemoryUserRepository) -> None:
        """Set up the repository.

        Args:
            store: The shared in-memory tables.
            users: Source of the owning user's cipher.
        """
        self._store = store
        self._users = users

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
            "debug_capture": False,
            "debug_capture_until": None,
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
            debug_capture=row["debug_capture"],
            debug_capture_until=row["debug_capture_until"],
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
        cipher = self._users._cipher(message.user_id)  # noqa: SLF001
        async with self._store.lock:
            existing = [
                row for row in self._store.messages.values()
                if row["game_session_id"] == message.game_session_id
            ]
            seq = max((row["seq"] for row in existing), default=0) + 1
            self._store.messages[message.message_id] = {
                "game_session_id": message.game_session_id,
                "user_id": message.user_id,
                "seq": seq,
                "role": message.role,
                "content_ct": cipher.encrypt(F_MESSAGE_CONTENT, message.content),
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
        """Read a page of a transcript, decrypting each message.

        Args:
            user_id: The owner.
            session_id: Which session.
            after_seq: Return messages after this position.
            limit: Page size.

        Returns:
            The messages, in order.
        """
        cipher = self._users._cipher(user_id)  # noqa: SLF001
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
                content=cipher.decrypt(F_MESSAGE_CONTENT, row["content_ct"]),
                input_mode=row["input_mode"],
                token_count=row["token_count"],
                created_at=row["created_at"],
            )
            for mid, row in rows[:limit]
        ]

    async def set_debug_capture(
        self, user_id: UUID, session_id: UUID, enabled: bool
    ) -> GameSession | None:
        """Turn the opt-in prompt capture on or off.

        Args:
            user_id: The owner.
            session_id: Which session.
            enabled: Whether to capture.

        Returns:
            The updated session, or ``None`` if it does not exist.
        """
        from datetime import timedelta

        row = self._store.sessions.get(session_id)
        if row is None or row["user_id"] != user_id:
            return None
        row["debug_capture"] = enabled
        # The 48-hour ceiling is applied here rather than trusted to the
        # caller, so there is no code path that can extend it.
        row["debug_capture_until"] = utc_now() + timedelta(hours=48) if enabled else None
        return await self.get_session(user_id, session_id)


def new_id() -> UUID:
    """Create a random identifier.

    Returns:
        A random UUID version 4. Random rather than sequential, so identifiers
        reveal nothing about how many accounts exist or in what order they were
        created — both of which a counting identifier would leak.
    """
    return uuid4()
