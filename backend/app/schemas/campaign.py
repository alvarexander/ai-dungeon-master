"""Request and response shapes for campaigns.

PHASE 1 STATUS: contract only, backed by the in-memory store. The URLs, field
names and validation rules are final; persistence arrives in Phase 2 with no
change to any of them.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from app.schemas.common import ApiModel

CampaignTitle = Annotated[str, StringConstraints(min_length=1, max_length=120, strip_whitespace=True)]
Ruleset = Literal["dnd5e", "freeform"]
Tone = Literal["heroic", "gritty", "comedic", "horror", "mystery"]


class CampaignCreateRequest(ApiModel):
    """Everything needed to begin a new story."""

    title: CampaignTitle = Field(
        description="Encrypted at rest — it is free text the player wrote.",
        examples=["The Hollow Beneath Redmoor"],
    )
    premise: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional opening situation. Also free text, also encrypted.",
        examples=["A mining village whose children have started sleepwalking to the old shaft."],
    )
    ruleset: Ruleset = Field(
        default="dnd5e",
        description="Which rules the Dungeon Master applies. A fixed value, stored in plaintext.",
        examples=["dnd5e"],
    )
    tone: Tone = Field(
        default="heroic",
        description="Steers the narration. A fixed value, safe in plaintext and useful in aggregate.",
        examples=["mystery"],
    )


class CampaignUpdateRequest(ApiModel):
    """Fields that may be changed after creation. All optional."""

    title: CampaignTitle | None = None
    premise: str | None = Field(default=None, max_length=2000)
    tone: Tone | None = None
    status: Literal["active", "archived"] | None = None


class CampaignSummary(ApiModel):
    """A campaign as it appears in a list."""

    campaign_id: str = Field(examples=["7e5a1d92-3c48-4b6f-a012-8d5e2f7c4b19"])
    title: str = Field(examples=["The Hollow Beneath Redmoor"])
    ruleset: Ruleset = Field(examples=["dnd5e"])
    tone: Tone = Field(examples=["mystery"])
    status: Literal["active", "archived"] = Field(examples=["active"])
    character_count: int = Field(examples=[1])
    updated_at: str = Field(
        description=(
            "Lists are ordered by this. They cannot be ordered by title, because the "
            "database cannot read encrypted titles — sorting by name happens after "
            "decryption, in this service."
        ),
        examples=["2026-09-06T10:22:31Z"],
    )


class CampaignDetail(CampaignSummary):
    """A campaign with its full detail."""

    premise: str | None = Field(
        default=None,
        examples=["A mining village whose children have started sleepwalking to the old shaft."],
    )
    created_at: str = Field(examples=["2026-09-01T18:04:00Z"])
