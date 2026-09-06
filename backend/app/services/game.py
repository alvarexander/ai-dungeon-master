"""The game loop: turning one player message into one Dungeon Master reply.

WHAT HAPPENS IN A TURN, IN ORDER
1. Find or create the campaign and the play session.
2. Load the recent conversation, decrypting it.
3. Scrub anything that looks like personal data out of what the player wrote.
4. Assemble the prompt: the Dungeon Master's instructions, the campaign, the
   character, the recent history.
5. Call Gemini.
6. Store both messages, encrypted.
7. Record a pseudonymous analytics event.
8. Return the narration.

WHY THIS LIVES IN A SERVICE RATHER THAN IN THE ENDPOINT
The endpoint's job is to speak HTTP: read the request, check the shape, return
a status code. The rules of the game belong here. That separation is what makes
this logic testable without pretending to be a web server, and it is why the
layering rule in ADR-010 exists.

Note also what this service does *not* do: it never touches the database
directly. It works with plain Python objects and hands them to repositories,
which encrypt them. Encryption cannot be forgotten here because it does not
happen here.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.repositories.base import (
    Campaign,
    CampaignRepository,
    CharacterRepository,
    GameSession,
    Message,
    SessionRepository,
    User,
)
from app.repositories.memory import new_id
from app.services.analytics import AnalyticsService
from app.services.dungeon_master import (
    HISTORY_WINDOW,
    TurnContext,
    build_contents,
    build_system_instruction,
    opening_scene_prompt,
)
from app.services.gemini import GeminiClient
from app.services.scrubber import scrub

_log = get_logger("game")

# How long a Dungeon Master reply may be, in tokens. Roughly 700 words — long
# enough for a rich scene, short enough that one turn cannot swallow a large
# share of the daily free allowance.
MAX_REPLY_TOKENS = 1024


@dataclass(frozen=True, slots=True)
class TurnOutcome:
    """Everything a completed turn produces.

    Attributes:
        session: The play session, created if this was the first turn.
        player_message: The player's stored message.
        dm_message: The Dungeon Master's stored reply.
        tokens_in: Tokens the prompt consumed.
        tokens_out: Tokens the reply consumed.
        latency_ms: How long the AI call took.
        model_id: Which model answered.
        scrubbed: Whether anything was removed from the outbound prompt.
    """

    session: GameSession
    player_message: Message
    dm_message: Message
    tokens_in: int
    tokens_out: int
    latency_ms: int
    model_id: str
    scrubbed: bool


class GameService:
    """Runs the conversation between a player and the Dungeon Master."""

    def __init__(
        self,
        *,
        campaigns: CampaignRepository,
        characters: CharacterRepository,
        sessions: SessionRepository,
        gemini: GeminiClient,
        analytics: AnalyticsService,
        scrub_outbound: bool,
    ) -> None:
        """Set up the service.

        Args:
            campaigns: Campaign storage.
            characters: Character storage.
            sessions: Session and transcript storage.
            gemini: The AI client.
            analytics: The pseudonymous event recorder.
            scrub_outbound: Whether to strip personal-data-shaped text from
                prompts before they leave. Configurable, and on by default,
                because Google's free tier terms permit training on prompts.
        """
        self._campaigns = campaigns
        self._characters = characters
        self._sessions = sessions
        self._gemini = gemini
        self._analytics = analytics
        self._scrub_outbound = scrub_outbound

    async def ensure_campaign(self, user: User, campaign_id: UUID | None) -> Campaign:
        """Find the requested campaign, or create a starter one.

        Args:
            user: The signed-in account.
            campaign_id: Which campaign, or ``None`` to use the most recent —
                creating a starter campaign if there is none at all, so a new
                player can begin typing without filling in a form first.

        Returns:
            The campaign to play in.

        Raises:
            NotFoundError: If a specific campaign was named and does not exist,
                or belongs to somebody else.
        """
        if campaign_id is not None:
            campaign = await self._campaigns.get(user.user_id, campaign_id)
            if campaign is None:
                raise NotFoundError("campaign")
            return campaign

        existing, _ = await self._campaigns.list_for_user(user.user_id, limit=1, offset=0)
        if existing:
            return existing[0]

        campaign = Campaign(
            campaign_id=new_id(),
            user_id=user.user_id,
            title="A Road Out of Redmoor",
            premise=(
                "A traveller arrives at a village where something has been going wrong "
                "quietly for a long time."
            ),
            ruleset="dnd5e",
            tone="mystery",
        )
        await self._campaigns.create(campaign)
        self._analytics.record(user.user_id, "campaign_created")
        _log.info("starter_campaign_created", user_id=str(user.user_id))
        return campaign

    async def ensure_session(
        self, user: User, campaign: Campaign, session_id: UUID | None
    ) -> GameSession:
        """Find the requested play session, or start a new one.

        Args:
            user: The signed-in account.
            campaign: The campaign being played.
            session_id: Which session to continue, or ``None`` to start one.

        Returns:
            The session to play in.

        Raises:
            NotFoundError: If a specific session was named and does not exist.
        """
        if session_id is not None:
            session = await self._sessions.get_session(user.user_id, session_id)
            if session is None:
                raise NotFoundError("session")
            return session

        session = GameSession(
            game_session_id=new_id(),
            campaign_id=campaign.campaign_id,
            user_id=user.user_id,
        )
        await self._sessions.create_session(session)
        self._analytics.record(user.user_id, "session_started")
        return session

    async def _character_summary(self, user: User, campaign: Campaign) -> str | None:
        """Describe the player's character in one line, for the prompt.

        Args:
            user: The signed-in account.
            campaign: The campaign being played.

        Returns:
            A short description such as "Wren Ashdown, a level 4 rogue", or
            ``None`` if no character exists yet.
        """
        characters = await self._characters.list_for_campaign(user.user_id, campaign.campaign_id)
        if not characters:
            return None
        character = characters[0]
        ancestry = character.sheet.get("ancestry")
        ancestry_text = f"{ancestry} " if ancestry else ""
        return (
            f"{character.name}, a level {character.level} "
            f"{ancestry_text}{character.character_class}"
        )

    async def take_turn(
        self,
        *,
        user: User,
        message_text: str,
        campaign_id: UUID | None,
        session_id: UUID | None,
        input_mode: str,
        country_code: str | None = None,
    ) -> TurnOutcome:
        """Run one full exchange with the Dungeon Master.

        Args:
            user: The signed-in account.
            message_text: What the player said.
            campaign_id: Which campaign, or ``None`` for the most recent.
            session_id: Which session, or ``None`` to start a new one.
            input_mode: ``"typed"`` or ``"voice"``. Recorded as a plain
                enumerated value for feature analytics.
            country_code: Two-letter country from the edge network, if present.

        Returns:
            The stored messages and the metrics for the turn.

        Raises:
            NotFoundError: If a named campaign or session does not exist.
            QuotaExhaustedError: If the AI allowance is used up.
            UpstreamAiError: If the AI call fails.
        """
        campaign = await self.ensure_campaign(user, campaign_id)
        session = await self.ensure_session(user, campaign, session_id)

        history = await self._sessions.list_messages(
            user.user_id, session.game_session_id, after_seq=0, limit=HISTORY_WINDOW
        )

        # The scrub happens here, on the way out, and only affects what is sent
        # to Google. The player's original words are stored unchanged, because
        # this is their own campaign and they are entitled to their own notes.
        outbound = message_text
        scrubbed = False
        if self._scrub_outbound:
            result = scrub(message_text)
            outbound = result.text
            scrubbed = result.changed
            if scrubbed:
                _log.info(
                    "prompt_scrubbed",
                    scrubbed_spans=result.replacements,
                    prompt_chars=len(message_text),
                )

        context = TurnContext(
            campaign_title=campaign.title,
            campaign_premise=campaign.premise,
            tone=campaign.tone,
            narration_length=user.settings.narration_length,
            content_filter=user.settings.content_filter,
            character_summary=await self._character_summary(user, campaign),
            history=history,
            player_message=outbound,
        )

        result = await self._gemini.generate(
            system_instruction=build_system_instruction(context),
            contents=build_contents(context),
            max_output_tokens=MAX_REPLY_TOKENS,
        )

        # Both messages are stored only after the AI call succeeds. Storing the
        # player's message first would leave orphaned half-turns in the
        # transcript every time Gemini is unavailable.
        player_message = await self._sessions.append_message(
            Message(
                message_id=new_id(),
                game_session_id=session.game_session_id,
                user_id=user.user_id,
                seq=0,  # assigned by the repository, under a lock
                role="player",
                content=message_text,
                input_mode=input_mode,
                token_count=result.tokens_in,
            )
        )
        dm_message = await self._sessions.append_message(
            Message(
                message_id=new_id(),
                game_session_id=session.game_session_id,
                user_id=user.user_id,
                seq=0,
                role="dungeon_master",
                content=result.text,
                input_mode="typed",
                token_count=result.tokens_out,
            )
        )

        if user.settings.analytics_opt_in:
            self._analytics.record(
                user.user_id,
                "turn_taken",
                country_code=country_code,
                turn_count=player_message.seq,
                feature="voice_input" if input_mode == "voice" else "typed_input",
                success=True,
            )
            if input_mode == "voice":
                self._analytics.record(
                    user.user_id, "voice_input_used", country_code=country_code
                )

        updated_session = await self._sessions.get_session(user.user_id, session.game_session_id)
        return TurnOutcome(
            session=updated_session or session,
            player_message=player_message,
            dm_message=dm_message,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            latency_ms=result.latency_ms,
            model_id=result.model_id,
            scrubbed=scrubbed,
        )

    async def open_campaign(self, user: User, campaign: Campaign) -> TurnOutcome:
        """Generate the opening scene for a brand new campaign.

        A new campaign has nothing for the model to react to, so instead of a
        player message it is given an instruction to set the scene.

        Args:
            user: The signed-in account.
            campaign: The campaign to open.

        Returns:
            The opening narration, stored as the first message.
        """
        return await self.take_turn(
            user=user,
            message_text=opening_scene_prompt(campaign.title, campaign.premise, campaign.tone),
            campaign_id=campaign.campaign_id,
            session_id=None,
            input_mode="typed",
        )
