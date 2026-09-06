"""Request and response shapes for player characters.

PHASE 1 STATUS: contract only, backed by the in-memory store.

A note on classification, because this table shows the reasoning clearly:
the character's *name* is encrypted, because players routinely use their own
name or a friend's. The character's *class and level* are plaintext, because
"level 4 rogue" identifies nobody and keeping it readable means questions like
"which class is most popular?" need no decryption at all.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from app.schemas.common import ApiModel

CharacterClass = Literal[
    "barbarian", "bard", "cleric", "druid", "fighter", "monk",
    "paladin", "ranger", "rogue", "sorcerer", "warlock", "wizard",
]

CharacterName = Annotated[str, StringConstraints(min_length=1, max_length=64, strip_whitespace=True)]


class AbilityScores(ApiModel):
    """The six Dungeons & Dragons ability scores.

    Bounded 1 to 30 because those are the limits the fifth-edition rules use.
    The bound is also input validation: it stops a submitted sheet containing
    a number large enough to break arithmetic elsewhere.
    """

    strength: int = Field(default=10, ge=1, le=30, examples=[12])
    dexterity: int = Field(default=10, ge=1, le=30, examples=[16])
    constitution: int = Field(default=10, ge=1, le=30, examples=[13])
    intelligence: int = Field(default=10, ge=1, le=30, examples=[10])
    wisdom: int = Field(default=10, ge=1, le=30, examples=[14])
    charisma: int = Field(default=10, ge=1, le=30, examples=[8])


class CharacterCreateRequest(ApiModel):
    """Everything needed to create a character."""

    name: CharacterName = Field(
        description="Encrypted at rest. Players use real names here more often than you would expect.",
        examples=["Wren Ashdown"],
    )
    character_class: CharacterClass = Field(
        description="A fixed value. Plaintext — it identifies nobody.", examples=["rogue"]
    )
    level: int = Field(default=1, ge=1, le=20, description="Plaintext.", examples=[4])
    ancestry: str | None = Field(
        default=None, max_length=48, description="Encrypted with the rest of the sheet.",
        examples=["Half-elf"],
    )
    abilities: AbilityScores = Field(default_factory=AbilityScores)
    backstory: str | None = Field(
        default=None,
        max_length=4000,
        description="Free text, therefore personal data, therefore encrypted.",
        examples=["Left the coast after a shipwreck she does not talk about."],
    )


class CharacterUpdateRequest(ApiModel):
    """Fields that may be changed. All optional."""

    name: CharacterName | None = None
    level: int | None = Field(default=None, ge=1, le=20)
    ancestry: str | None = Field(default=None, max_length=48)
    abilities: AbilityScores | None = None
    backstory: str | None = Field(default=None, max_length=4000)
    hit_points_current: int | None = Field(default=None, ge=0, le=999)


class CharacterDetail(ApiModel):
    """A character sheet, decrypted for this response only."""

    character_id: str = Field(examples=["1a7c3e58-6b90-4d21-a4f7-2e8c5b0d9f34"])
    campaign_id: str = Field(examples=["7e5a1d92-3c48-4b6f-a012-8d5e2f7c4b19"])
    name: str = Field(examples=["Wren Ashdown"])
    character_class: CharacterClass = Field(examples=["rogue"])
    level: int = Field(examples=[4])
    ancestry: str | None = Field(default=None, examples=["Half-elf"])
    abilities: AbilityScores
    hit_points_current: int = Field(examples=[27])
    hit_points_max: int = Field(examples=[31])
    backstory: str | None = Field(
        default=None, examples=["Left the coast after a shipwreck she does not talk about."]
    )
    created_at: str = Field(examples=["2026-09-01T18:10:00Z"])
    updated_at: str = Field(examples=["2026-09-06T10:22:31Z"])
