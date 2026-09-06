"""Request and response shapes for the conversation with the Dungeon Master.

This is the one part of Phase 1 that is fully real: a message goes in, Gemini
is called, and the Dungeon Master's narration comes back.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.common import ApiModel

# The upper bound on a player's message. Long enough for a paragraph of
# roleplay, short enough that it cannot be used to run up token costs or to
# push earlier turns out of the model's memory in a single message.
MAX_MESSAGE_CHARS = 4000


class ChatTurnRequest(ApiModel):
    """One thing the player says to the Dungeon Master."""

    message: str = Field(
        min_length=1,
        max_length=MAX_MESSAGE_CHARS,
        description=(
            "What the player says or does. Treated as personal data throughout: "
            "players type their own and their friends' real names into free text, so it "
            "is encrypted at rest and scrubbed before being sent to Google."
        ),
        examples=["I push open the chapel door and hold up the lantern."],
    )
    session_id: str | None = Field(
        default=None,
        description="Continue an existing play session. Omit to start a new one.",
        examples=["4b2f8c10-9d3a-4e57-8f21-6a0b3c9d1e42"],
    )
    campaign_id: str | None = Field(
        default=None,
        description="Which campaign this belongs to. Omit to use the demo campaign.",
        examples=["7e5a1d92-3c48-4b6f-a012-8d5e2f7c4b19"],
    )
    input_mode: Literal["typed", "voice"] = Field(
        default="typed",
        description=(
            "How the player entered this. Recorded as a plain enumerated value for "
            "feature analytics — it says which button was used, nothing about the person."
        ),
        examples=["typed"],
    )


class TokenUsage(ApiModel):
    """How much of the AI allowance one turn consumed.

    A "token" is roughly three-quarters of a word — the unit models count in.
    Surfacing this lets you see the free tier being consumed in real time
    rather than discovering it when requests start failing.
    """

    tokens_in: int = Field(description="Tokens in the prompt sent.", examples=[820])
    tokens_out: int = Field(description="Tokens in the reply received.", examples=[240])
    model_id: str = Field(description="Which model answered.", examples=["gemini-3.5-flash"])
    latency_ms: int = Field(description="How long the call took.", examples=[2140])


class ChatTurnResponse(ApiModel):
    """The Dungeon Master's reply to one player message."""

    session_id: str = Field(
        description="The play session, created on the first turn.",
        examples=["4b2f8c10-9d3a-4e57-8f21-6a0b3c9d1e42"],
    )
    message_id: str = Field(examples=["b91d4e77-5a2c-4f18-9e63-0c8a7b5d3f21"])
    reply: str = Field(
        description="The narration, in character.",
        examples=[
            "The door gives with a groan of swollen wood. Your lantern throws long "
            "shadows across a floor thick with dust — and a single set of footprints, "
            "leading in. They are fresh. What do you do?"
        ],
    )
    turn: int = Field(description="Which exchange this is in the session.", examples=[7])
    usage: TokenUsage
    scrubbed: bool = Field(
        default=False,
        description=(
            "True if the outbound prompt had personal-data-looking text removed before "
            "it left this server. Surfaced so the behaviour is visible, not silent."
        ),
    )


class TranscriptMessage(ApiModel):
    """One stored message, decrypted for this response only."""

    message_id: str = Field(examples=["b91d4e77-5a2c-4f18-9e63-0c8a7b5d3f21"])
    seq: int = Field(description="Position in the conversation.", examples=[7])
    role: Literal["player", "dungeon_master", "system"] = Field(examples=["dungeon_master"])
    content: str = Field(
        description="The words. Encrypted at rest; plaintext only here, in this response.",
        examples=["The door gives with a groan of swollen wood."],
    )
    input_mode: Literal["typed", "voice"] = Field(examples=["typed"])
    created_at: str = Field(examples=["2026-09-06T10:22:31Z"])


