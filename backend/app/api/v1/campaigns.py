"""Campaigns: the long-running stories.

PHASE 1 STATUS: fully working against the in-memory store, with real
encryption. Everything survives until the server restarts.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import ContainerDep, CurrentUser
from app.core.errors import NotFoundError
from app.repositories.base import Campaign
from app.repositories.memory import new_id
from app.schemas.campaign import (
    CampaignCreateRequest,
    CampaignDetail,
    CampaignSummary,
    CampaignUpdateRequest,
)
from app.schemas.common import Acknowledgement, ErrorResponse, Page

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


def _iso(value: object) -> str:
    """Format a timestamp for the API.

    Args:
        value: A timezone-aware datetime.

    Returns:
        An ISO-8601 string ending in ``Z``, which is what browsers parse most
        reliably.
    """
    return value.isoformat().replace("+00:00", "Z")  # type: ignore[attr-defined]


async def _summary(campaign: Campaign, container: ContainerDep, user_id: UUID) -> CampaignSummary:
    """Build the list-view shape for one campaign.

    Args:
        campaign: The decrypted campaign.
        container: The application container.
        user_id: The owner.

    Returns:
        The summary.
    """
    characters = await container.characters.list_for_campaign(user_id, campaign.campaign_id)
    return CampaignSummary(
        campaign_id=str(campaign.campaign_id),
        title=campaign.title,
        ruleset=campaign.ruleset,  # type: ignore[arg-type]
        tone=campaign.tone,  # type: ignore[arg-type]
        status=campaign.status,  # type: ignore[arg-type]
        character_count=len(characters),
        updated_at=_iso(campaign.updated_at),
    )


@router.get("", response_model=Page[CampaignSummary], summary="List your campaigns")
async def list_campaigns(
    user: CurrentUser,
    container: ContainerDep,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Page[CampaignSummary]:
    """List the signed-in user's campaigns, most recently played first.

    Ordered by time rather than by title. That is not a preference: campaign
    titles are encrypted, so the storage layer genuinely cannot sort by them.
    Sorting by name would require decrypting every campaign first, which is why
    the page size is capped.

    Args:
        user: The account making the request.
        container: The application container.
        limit: Page size.
        offset: How many to skip.

    Returns:
        A page of campaign summaries.
    """
    campaigns, total = await container.campaigns.list_for_user(user.user_id, limit, offset)
    return Page[CampaignSummary](
        items=[await _summary(campaign, container, user.user_id) for campaign in campaigns],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=CampaignDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new campaign",
)
async def create_campaign(
    payload: CampaignCreateRequest, user: CurrentUser, container: ContainerDep
) -> CampaignDetail:
    """Create a campaign.

    The title and premise are free text the player wrote, so both are encrypted
    before storage. The ruleset and tone are fixed values from a list, so they
    stay readable — which is what lets questions like "how many campaigns use
    the horror tone?" be answered without decrypting anything.

    Args:
        payload: The campaign details.
        user: The account making the request.
        container: The application container.

    Returns:
        The created campaign.
    """
    campaign = Campaign(
        campaign_id=new_id(),
        user_id=user.user_id,
        title=payload.title,
        premise=payload.premise,
        ruleset=payload.ruleset,
        tone=payload.tone,
    )
    await container.campaigns.create(campaign)
    if user.settings.analytics_opt_in:
        container.analytics.record(user.user_id, "campaign_created")

    return CampaignDetail(
        campaign_id=str(campaign.campaign_id),
        title=campaign.title,
        premise=campaign.premise,
        ruleset=campaign.ruleset,  # type: ignore[arg-type]
        tone=campaign.tone,  # type: ignore[arg-type]
        status="active",
        character_count=0,
        created_at=_iso(campaign.created_at),
        updated_at=_iso(campaign.updated_at),
    )


@router.get(
    "/{campaign_id}",
    response_model=CampaignDetail,
    responses={404: {"model": ErrorResponse, "description": "No such campaign."}},
    summary="Read one campaign",
)
async def get_campaign(
    campaign_id: UUID, user: CurrentUser, container: ContainerDep
) -> CampaignDetail:
    """Fetch one campaign, decrypting its text.

    Args:
        campaign_id: Which campaign.
        user: The account making the request.
        container: The application container.

    Returns:
        The campaign.

    Raises:
        NotFoundError: If it does not exist, or belongs to someone else. Both
            produce the same 404, so guessing identifiers reveals nothing.
    """
    campaign = await container.campaigns.get(user.user_id, campaign_id)
    if campaign is None:
        raise NotFoundError("campaign")
    characters = await container.characters.list_for_campaign(user.user_id, campaign_id)
    return CampaignDetail(
        campaign_id=str(campaign.campaign_id),
        title=campaign.title,
        premise=campaign.premise,
        ruleset=campaign.ruleset,  # type: ignore[arg-type]
        tone=campaign.tone,  # type: ignore[arg-type]
        status=campaign.status,  # type: ignore[arg-type]
        character_count=len(characters),
        created_at=_iso(campaign.created_at),
        updated_at=_iso(campaign.updated_at),
    )


@router.patch("/{campaign_id}", response_model=CampaignDetail, summary="Change a campaign")
async def update_campaign(
    campaign_id: UUID,
    payload: CampaignUpdateRequest,
    user: CurrentUser,
    container: ContainerDep,
) -> CampaignDetail:
    """Change some of a campaign's fields.

    A partial update: omitted fields are left alone. Changed text fields are
    re-encrypted, with a fresh random nonce, so the new ciphertext bears no
    resemblance to the old even if the text barely changed.

    Args:
        campaign_id: Which campaign.
        payload: The fields to change.
        user: The account making the request.
        container: The application container.

    Returns:
        The updated campaign.

    Raises:
        NotFoundError: If it does not exist or is not the caller's.
    """
    campaign = await container.campaigns.get(user.user_id, campaign_id)
    if campaign is None:
        raise NotFoundError("campaign")

    if payload.title is not None:
        campaign.title = payload.title
    if payload.premise is not None:
        campaign.premise = payload.premise
    if payload.tone is not None:
        campaign.tone = payload.tone
    if payload.status is not None:
        campaign.status = payload.status

    updated = await container.campaigns.update(campaign)
    return await get_campaign(updated.campaign_id, user, container)


@router.delete("/{campaign_id}", response_model=Acknowledgement, summary="Delete a campaign")
async def delete_campaign(
    campaign_id: UUID, user: CurrentUser, container: ContainerDep
) -> Acknowledgement:
    """Delete a campaign and everything in it.

    Args:
        campaign_id: Which campaign.
        user: The account making the request.
        container: The application container.

    Returns:
        A confirmation.

    Raises:
        NotFoundError: If it does not exist or is not the caller's.
    """
    if not await container.campaigns.delete(user.user_id, campaign_id):
        raise NotFoundError("campaign")
    return Acknowledgement(detail="Campaign deleted.")
