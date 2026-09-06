"""Player characters and their sheets.

PHASE 1 STATUS: fully working against the in-memory store, with real
encryption of the name, backstory and sheet.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import ContainerDep, CurrentUser
from app.core.errors import NotFoundError
from app.repositories.base import Character
from app.repositories.memory import new_id
from app.schemas.character import (
    AbilityScores,
    CharacterCreateRequest,
    CharacterDetail,
    CharacterUpdateRequest,
)
from app.schemas.common import Acknowledgement, ErrorResponse

router = APIRouter(tags=["characters"])

# Average hit points per level by class, used to give a new character sensible
# starting health without making the player do arithmetic.
_HIT_DIE_AVERAGE: dict[str, int] = {
    "barbarian": 7, "fighter": 6, "paladin": 6, "ranger": 6,
    "bard": 5, "cleric": 5, "druid": 5, "monk": 5, "rogue": 5, "warlock": 5,
    "sorcerer": 4, "wizard": 4,
}


def _ability_modifier(score: int) -> int:
    """Convert an ability score into its modifier, per the fifth-edition rules.

    A score of 10 is average and gives no bonus; every two points above or
    below shifts the modifier by one.

    Args:
        score: The ability score, 1 to 30.

    Returns:
        The modifier, which may be negative.
    """
    return (score - 10) // 2


def _max_hit_points(character_class: str, level: int, constitution: int) -> int:
    """Work out a character's maximum health.

    First level grants the full hit die; later levels grant the average. The
    constitution modifier is added for every level.

    Args:
        character_class: Which class, determining the hit die size.
        level: The character's level.
        constitution: Their constitution score.

    Returns:
        Maximum hit points, never below one — a character with a terrible
        constitution should be fragile, not already dead.
    """
    average = _HIT_DIE_AVERAGE.get(character_class, 5)
    first_level = average * 2  # the full die at first level
    modifier = _ability_modifier(constitution)
    return max(1, first_level + (level - 1) * average + modifier * level)


def _detail(character: Character) -> CharacterDetail:
    """Build the API response shape from a decrypted character.

    Args:
        character: The character, already decrypted.

    Returns:
        The response model.
    """
    sheet: dict[str, Any] = character.sheet
    abilities = AbilityScores(**sheet.get("abilities", {}))
    return CharacterDetail(
        character_id=str(character.character_id),
        campaign_id=str(character.campaign_id),
        name=character.name,
        character_class=character.character_class,  # type: ignore[arg-type]
        level=character.level,
        ancestry=sheet.get("ancestry"),
        abilities=abilities,
        hit_points_current=sheet.get("hit_points_current", 1),
        hit_points_max=sheet.get("hit_points_max", 1),
        backstory=sheet.get("backstory"),
        created_at=character.created_at.isoformat().replace("+00:00", "Z"),
        updated_at=character.updated_at.isoformat().replace("+00:00", "Z"),
    )


@router.get(
    "/campaigns/{campaign_id}/characters",
    response_model=list[CharacterDetail],
    summary="List the characters in a campaign",
)
async def list_characters(
    campaign_id: UUID, user: CurrentUser, container: ContainerDep
) -> list[CharacterDetail]:
    """List every character in one campaign, decrypting each sheet.

    Args:
        campaign_id: Which campaign.
        user: The account making the request.
        container: The application container.

    Returns:
        The characters.

    Raises:
        NotFoundError: If the campaign does not exist or is not the caller's.
    """
    if await container.campaigns.get(user.user_id, campaign_id) is None:
        raise NotFoundError("campaign")
    characters = await container.characters.list_for_campaign(user.user_id, campaign_id)
    return [_detail(character) for character in characters]


@router.post(
    "/campaigns/{campaign_id}/characters",
    response_model=CharacterDetail,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse, "description": "No such campaign."}},
    summary="Create a character",
)
async def create_character(
    campaign_id: UUID,
    payload: CharacterCreateRequest,
    user: CurrentUser,
    container: ContainerDep,
) -> CharacterDetail:
    """Create a character and compute its starting health.

    Note the classification split, which this endpoint shows clearly. The
    character's **name** and **backstory** are encrypted, because players
    routinely use their own name or a friend's. The **class** and **level** are
    stored in plaintext, because "level 4 rogue" identifies nobody and keeping
    them readable means aggregate questions need no decryption at all.

    Args:
        campaign_id: Which campaign the character belongs to.
        payload: The character's details.
        user: The account making the request.
        container: The application container.

    Returns:
        The created character.

    Raises:
        NotFoundError: If the campaign does not exist or is not the caller's.
    """
    if await container.campaigns.get(user.user_id, campaign_id) is None:
        raise NotFoundError("campaign")

    hit_points = _max_hit_points(
        payload.character_class, payload.level, payload.abilities.constitution
    )
    character = Character(
        character_id=new_id(),
        campaign_id=campaign_id,
        user_id=user.user_id,
        name=payload.name,
        character_class=payload.character_class,
        level=payload.level,
        sheet={
            "ancestry": payload.ancestry,
            "abilities": payload.abilities.model_dump(),
            "backstory": payload.backstory,
            "hit_points_max": hit_points,
            "hit_points_current": hit_points,
            "inventory": [],
            "notes": "",
        },
    )
    await container.characters.create(character)
    if user.settings.analytics_opt_in:
        container.analytics.record(user.user_id, "character_created", feature="character_sheet")
    return _detail(character)


@router.get("/characters/{character_id}", response_model=CharacterDetail, summary="Read a character")
async def get_character(
    character_id: UUID, user: CurrentUser, container: ContainerDep
) -> CharacterDetail:
    """Fetch one character sheet, decrypted.

    Args:
        character_id: Which character.
        user: The account making the request.
        container: The application container.

    Returns:
        The character sheet.

    Raises:
        NotFoundError: If it does not exist or is not the caller's.
    """
    character = await container.characters.get(user.user_id, character_id)
    if character is None:
        raise NotFoundError("character")
    return _detail(character)


@router.patch("/characters/{character_id}", response_model=CharacterDetail, summary="Change a character")
async def update_character(
    character_id: UUID,
    payload: CharacterUpdateRequest,
    user: CurrentUser,
    container: ContainerDep,
) -> CharacterDetail:
    """Change some of a character's fields.

    Args:
        character_id: Which character.
        payload: The fields to change. Omitted fields are left alone.
        user: The account making the request.
        container: The application container.

    Returns:
        The updated character.

    Raises:
        NotFoundError: If it does not exist or is not the caller's.
    """
    character = await container.characters.get(user.user_id, character_id)
    if character is None:
        raise NotFoundError("character")

    if payload.name is not None:
        character.name = payload.name
    if payload.level is not None:
        character.level = payload.level
    if payload.ancestry is not None:
        character.sheet["ancestry"] = payload.ancestry
    if payload.backstory is not None:
        character.sheet["backstory"] = payload.backstory
    if payload.abilities is not None:
        character.sheet["abilities"] = payload.abilities.model_dump()
        # Health depends on constitution and level, so recompute it whenever
        # either changes rather than leaving a stale number on the sheet.
        character.sheet["hit_points_max"] = _max_hit_points(
            character.character_class, character.level, payload.abilities.constitution
        )
    if payload.hit_points_current is not None:
        character.sheet["hit_points_current"] = min(
            payload.hit_points_current, character.sheet.get("hit_points_max", 1)
        )

    updated = await container.characters.update(character)
    if user.settings.analytics_opt_in:
        container.analytics.record(user.user_id, "character_updated", feature="character_sheet")
    return _detail(updated)


@router.delete("/characters/{character_id}", response_model=Acknowledgement, summary="Delete a character")
async def delete_character(
    character_id: UUID, user: CurrentUser, container: ContainerDep
) -> Acknowledgement:
    """Delete a character.

    Args:
        character_id: Which character.
        user: The account making the request.
        container: The application container.

    Returns:
        A confirmation.

    Raises:
        NotFoundError: If it does not exist or is not the caller's.
    """
    if not await container.characters.delete(user.user_id, character_id):
        raise NotFoundError("character")
    return Acknowledgement(detail="Character deleted.")
