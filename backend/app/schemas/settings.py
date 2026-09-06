"""Request and response shapes for user settings and account management.

PHASE 1 STATUS: contract only, backed by the in-memory store.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.common import ApiModel


class UserSettings(ApiModel):
    """Preferences belonging to one account.

    Every field here is an enumerated value or a boolean. None of it is
    personal data, so all of it can be stored in plaintext — which is why
    settings can be read without a key and without a decryption call.
    """

    narration_length: Literal["brief", "standard", "rich"] = Field(
        default="standard",
        description="How much the Dungeon Master writes per turn.",
        examples=["standard"],
    )
    dice_rolls_visible: bool = Field(
        default=True, description="Show dice results, or keep them behind the screen.", examples=[True]
    )
    content_filter: Literal["family", "standard", "mature"] = Field(
        default="standard",
        description="Steers the tone of what the Dungeon Master will describe.",
        examples=["standard"],
    )
    voice_input_enabled: bool = Field(default=True, examples=[True])
    voice_autosend: bool = Field(
        default=False,
        description="Send automatically when speech stops, rather than waiting for a press.",
        examples=[False],
    )
    theme: Literal["dark", "light", "system"] = Field(default="dark", examples=["dark"])
    reduce_motion: bool = Field(
        default=False, description="Honour reduced-motion preferences for animations.", examples=[False]
    )
    analytics_opt_in: bool = Field(
        default=True,
        description=(
            "Whether pseudonymous usage counts are recorded. Even when on, no free text "
            "and no personal data enters analytics — there is physically no column for it."
        ),
        examples=[True],
    )


class SettingsUpdateRequest(ApiModel):
    """A partial update. Every field is optional; omitted fields are unchanged."""

    narration_length: Literal["brief", "standard", "rich"] | None = None
    dice_rolls_visible: bool | None = None
    content_filter: Literal["family", "standard", "mature"] | None = None
    voice_input_enabled: bool | None = None
    voice_autosend: bool | None = None
    theme: Literal["dark", "light", "system"] | None = None
    reduce_motion: bool | None = None
    analytics_opt_in: bool | None = None


class AccountDeletionRequest(ApiModel):
    """Confirmation required to permanently destroy an account."""

    confirm_username: str = Field(
        description=(
            "The account's username, typed again. A deliberate friction step, because "
            "this permanently removes every campaign, character and conversation."
        ),
        examples=["torchbearer"],
    )
    understood: bool = Field(
        description="Must be true. The interface only sets it after the warning is shown.",
        examples=[True],
    )


class AccountDeletionResponse(ApiModel):
    """Confirmation that an account and all its data were deleted."""

    user_id: str = Field(examples=["9c1e5b70-2b6a-4a4e-9d6a-2f0c1b5e7a31"])
    deleted_at: str = Field(examples=["2026-09-06T11:00:00Z"])
    detail: str = Field(
        examples=[
            "Your account has been deleted, along with every campaign, character and "
            "conversation."
        ]
    )


class ActivityEntry(ApiModel):
    """One line in the user's own visible account history.

    This is where "support looked at your data" appears. If we read someone's
    records, they are told, and this is where they see it.
    """

    event_type: Literal[
        "login", "logout", "password_changed", "email_changed",
        "support_access", "data_exported", "deletion_requested",
    ] = Field(examples=["support_access"])
    detail: str | None = Field(
        default=None,
        description="Decrypted for this response only.",
        examples=["Support reviewed a failing session at your request. Reason: reported error."],
    )
    occurred_at: str = Field(examples=["2026-09-05T14:02:11Z"])
