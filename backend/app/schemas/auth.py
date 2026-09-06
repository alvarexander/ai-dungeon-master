"""Request and response shapes for registration, login, and the account.

PHASE 1 STATUS: STUBBED
Every endpoint using these models runs, validates its input, applies rate
limits, and returns a correctly shaped reply — but it does not yet check a real
password against a real stored account, because there is no database. The
models, the validation rules, and the URL contract are final; only the body of
the service behind them is temporary. See `app/services/auth.py`, where every
stub is marked.
"""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import EmailStr, Field, StringConstraints, field_validator

from app.schemas.common import ApiModel

# A username is 3 to 32 characters of letters, digits, underscore and hyphen.
# Deliberately narrow: it appears in plaintext in the database, so it must not
# be able to hold an email address or a sentence someone typed by mistake.
Username = Annotated[
    str,
    StringConstraints(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_-]+$", strip_whitespace=True),
]

DisplayName = Annotated[str, StringConstraints(min_length=1, max_length=64, strip_whitespace=True)]

# 12 characters is the floor. Length beats complexity rules: "correct horse
# battery staple" is far stronger than "P@ssw0rd!" and far easier to remember.
# The upper bound of 200 exists so that an enormous submission cannot be used
# to make the server do expensive hashing work — a denial-of-service through
# the password field.
Password = Annotated[str, StringConstraints(min_length=12, max_length=200)]


class RegisterRequest(ApiModel):
    """Everything needed to create an account."""

    username: Username = Field(
        description="Public handle. Stored in plaintext — classified as non-personal.",
        examples=["torchbearer"],
    )
    display_name: DisplayName = Field(
        description="Name shown in the interface. Also plaintext by classification.",
        examples=["The Torchbearer"],
    )
    email: EmailStr = Field(
        description=(
            "Encrypted at rest. Only a keyed fingerprint of it is searchable, and the "
            "key for that fingerprint is never stored in the database."
        ),
        examples=["player@example.com"],
    )
    password: Password = Field(
        description=(
            "Hashed with Argon2id, never encrypted and never recoverable. Minimum 12 "
            "characters — a long passphrase is stronger than a short complicated one."
        ),
        examples=["correct-horse-battery-staple"],
    )

    @field_validator("password")
    @classmethod
    def _reject_obvious_passwords(cls, value: str) -> str:
        """Reject a handful of passwords that appear in every breach list.

        This is not a substitute for a full compromised-password check, which
        belongs in Phase 2 and needs an external dataset. It catches the worst
        cases at zero cost.

        Args:
            value: The submitted password.

        Returns:
            The password unchanged, if acceptable.

        Raises:
            ValueError: If the password is trivially guessable. The message
                deliberately does not echo the password back, because
                validation errors are written to logs.
        """
        lowered = value.lower()
        obvious = ("password", "123456", "qwerty", "letmein", "dungeon", "dragon")
        if any(lowered.startswith(term) for term in obvious):
            raise ValueError(
                "That password starts with one of the most commonly guessed words. "
                "Please choose something less predictable."
            )
        if re.fullmatch(r"(.)\1+", value):
            raise ValueError("That password is a single repeated character.")
        return value


class LoginRequest(ApiModel):
    """Credentials submitted at sign-in."""

    identifier: str = Field(
        min_length=1,
        max_length=254,
        description=(
            "Email address or username. When it contains an '@' it is turned into a "
            "blind-index fingerprint for lookup; otherwise it is matched against the "
            "plaintext username column."
        ),
        examples=["player@example.com"],
    )
    password: str = Field(
        min_length=1,
        max_length=200,
        description="The password. Never logged, at any level, under any configuration.",
        examples=["correct-horse-battery-staple"],
    )


class UserProfile(ApiModel):
    """The account as the signed-in user sees it.

    Everything here except the identifiers arrives decrypted, in memory, for
    this one response. It is never cached and never logged.
    """

    user_id: str = Field(
        description="Opaque random identifier. Safe to log and safe to put in a bug report.",
        examples=["9c1e5b70-2b6a-4a4e-9d6a-2f0c1b5e7a31"],
    )
    username: str = Field(examples=["torchbearer"])
    display_name: str = Field(examples=["The Torchbearer"])
    email: EmailStr = Field(
        description="Decrypted for this response only.", examples=["player@example.com"]
    )
    email_verified: bool = Field(examples=[False])
    created_at: str = Field(
        description="Account creation time, ISO-8601 in UTC.", examples=["2026-09-06T10:15:00Z"]
    )
    is_stub: bool = Field(
        default=True,
        description=(
            "True while authentication is not yet implemented. The frontend uses this "
            "to show its 'demo mode' banner, so a mock is never mistaken for real."
        ),
    )


class LoginResponse(ApiModel):
    """What a successful sign-in returns."""

    access_token: str = Field(
        description=(
            "Bearer token for authenticated requests. In Phase 1 this is a clearly "
            "marked placeholder that grants access to a synthetic account only."
        ),
        examples=["stub.eyJzdWIiOiJkZW1vIn0.not-a-real-token"],
    )
    token_type: str = Field(default="bearer", examples=["bearer"])
    expires_in: int = Field(description="Lifetime in seconds.", examples=[3600])
    user: UserProfile
    is_stub: bool = Field(default=True, description="True while authentication is stubbed.")


class XsrfTokenResponse(ApiModel):
    """The cross-site request forgery token, returned in the body as well as a cookie.

    The cookie is the primary mechanism. This body copy exists so the frontend
    can confirm at startup that it successfully obtained a token, and so that
    the failure mode — frontend and backend on unrelated domains — produces a
    clear diagnostic instead of mysterious 403 responses later.
    """

    token: str = Field(
        description="Also set as a cookie. Echo it in the X-XSRF-TOKEN header.",
        examples=["p8Zx1QeR3kT7vN2sYbH0aWcLd5FgJ9mE"],
    )
    header_name: str = Field(examples=["X-XSRF-TOKEN"])
    cookie_name: str = Field(examples=["XSRF-TOKEN"])
