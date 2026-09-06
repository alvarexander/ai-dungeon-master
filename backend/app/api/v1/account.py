"""User settings, the activity log, and account deletion."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ContainerDep, CurrentUser
from app.core.errors import ApiError
from app.schemas.common import ErrorResponse
from app.schemas.settings import (
    AccountDeletionRequest,
    AccountDeletionResponse,
    ActivityEntry,
    SettingsUpdateRequest,
    UserSettings,
)

router = APIRouter(tags=["account"])


@router.get("/settings", response_model=UserSettings, summary="Read your settings")
async def get_settings_endpoint(user: CurrentUser) -> UserSettings:
    """Return the signed-in user's preferences.

    Worth noticing: this endpoint performs no decryption at all. Every setting
    is an enumerated value or a boolean, none of which is personal data, so
    they are stored in plaintext and can be read without touching a key.

    Args:
        user: The account making the request.

    Returns:
        The current settings.
    """
    return user.settings


@router.patch("/settings", response_model=UserSettings, summary="Change your settings")
async def update_settings(
    payload: SettingsUpdateRequest, user: CurrentUser, container: ContainerDep
) -> UserSettings:
    """Change some settings, leaving the rest alone.

    Args:
        payload: The fields to change.
        user: The account making the request.
        container: The application container.

    Returns:
        The complete updated settings.
    """
    merged = user.settings.model_dump()
    merged.update({key: value for key, value in payload.model_dump().items() if value is not None})
    settings = UserSettings(**merged)
    await container.users.update_settings(user.user_id, settings)
    if settings.analytics_opt_in:
        container.analytics.record(user.user_id, "settings_changed", feature="settings")
    return settings


@router.get("/account/activity", response_model=list[ActivityEntry], summary="Your account activity")
async def account_activity(user: CurrentUser) -> list[ActivityEntry]:
    """Return the user's own view of what has happened to their account.

    This is where a player sees "support accessed your data on Tuesday, and
    here is the reason they gave". The design commits to telling people when
    their data is read, and this endpoint is that commitment made visible.

    Phase 1 returns the account's creation. Phase 2 reads the
    ``account_activity_log`` table, whose ``detail`` column is encrypted under
    the user's own key.

    Args:
        user: The account making the request.

    Returns:
        The activity entries, newest first.
    """
    return [
        ActivityEntry(
            event_type="login",
            detail="Account created and signed in.",
            occurred_at=user.created_at.isoformat().replace("+00:00", "Z"),
        )
    ]


@router.post(
    "/account/delete",
    response_model=AccountDeletionResponse,
    responses={400: {"model": ErrorResponse, "description": "Confirmation did not match."}},
    summary="Permanently delete your account",
)
async def delete_account(
    payload: AccountDeletionRequest, user: CurrentUser, container: ContainerDep
) -> AccountDeletionResponse:
    """Delete the account and everything belonging to it.

    Campaigns, characters, play sessions and every message are removed. In
    MySQL that happens through the ``ON DELETE CASCADE`` rules in the schema,
    so nothing is left behind for a later cleanup job to forget.

    The link to the account's analytics is severed in the same operation. Past
    activity keeps contributing to aggregate totals, but nothing can ever
    attribute it to a person again.

    **One honest limitation:** this does not reach into database backups. A
    backup taken before the deletion still holds the rows, encrypted, until it
    ages out of the retention window.

    Args:
        payload: The typed confirmation.
        user: The account making the request.
        container: The application container.

    Returns:
        Proof of deletion, with the time the key was destroyed.

    Raises:
        ApiError: If the confirmation does not match. Deliberate friction on an
            action nobody, including us, can undo.
    """
    if payload.confirm_username != user.username or not payload.understood:
        raise ApiError(
            400,
            "confirmation_required",
            "To delete your account, type your username exactly and confirm that you "
            "understand this cannot be undone.",
        )

    container.analytics.forget(user.user_id)
    deleted_at = await container.auth.delete_account(user.user_id)

    return AccountDeletionResponse(
        user_id=str(user.user_id),
        deleted_at=deleted_at.isoformat().replace("+00:00", "Z"),
        detail=(
            "Your account has been deleted, along with every campaign, character and "
            "conversation. Your past activity remains only as anonymous totals that "
            "cannot be traced back to you. Database backups taken before now still hold "
            "your data in encrypted form until they age out."
        ),
    )
