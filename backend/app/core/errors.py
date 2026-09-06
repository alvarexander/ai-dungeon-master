"""One consistent error shape for the whole API.

WHY ERRORS NEED A DESIGN
An error message is a message to two audiences at once: the person using the
application, who needs to know what to do next, and an attacker, who is reading
it for clues. Those audiences want opposite things, so every error in this
application is written deliberately.

The rules:

1. **Every error carries the correlation identifier.** The user can read it out
   when reporting a problem, and it is the only thing needed to find the full
   story in the logs. This is what replaces "let me look at your account".
2. **Errors never contain personal data.** Not the email that failed to
   validate, not the message that was too long. The field name, yes; its
   contents, never.
3. **Authentication errors are deliberately vague.** "Invalid credentials"
   whether the account exists or not. Saying "no such user" would let an
   attacker map out who is registered, defeating the encrypted email column.
4. **Unexpected errors reveal nothing.** A crash returns a generic message and
   an identifier. The stack trace goes to the logs, not to the browser.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.correlation import get_correlation_id
from app.core.logging import get_logger

_log = get_logger("errors")


class ApiError(Exception):
    """An error that is safe to show the user, with a machine-readable code.

    Attributes:
        status_code: The HTTP status to return.
        code: A short stable string such as ``"rate_limited"``. The frontend
            branches on this, never on the human-readable message, so wording
            can be improved without breaking the client.
        message: A plain-language explanation, free of personal data.
        headers: Extra response headers, such as ``Retry-After``.
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Create an error.

        Args:
            status_code: The HTTP status code.
            code: The stable machine-readable code.
            message: The human-readable explanation.
            headers: Any extra response headers.
        """
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers or {}


class RateLimitedError(ApiError):
    """Raised when a caller has exceeded a rate limit."""

    def __init__(self, retry_after_seconds: int, scope: str) -> None:
        """Create the error.

        Args:
            retry_after_seconds: How long until the caller may try again.
            scope: Which limit was exceeded, for the log. Included in the
                message because knowing *which* limit you hit is genuinely
                useful and tells an attacker nothing they did not already know.
        """
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="rate_limited",
            message=(
                f"Too many requests. Please wait {retry_after_seconds} seconds and try again."
            ),
            headers={"Retry-After": str(retry_after_seconds)},
        )
        self.scope = scope


class UpstreamAiError(ApiError):
    """Raised when Gemini fails, is unreachable, or refuses to answer."""

    def __init__(self, message: str, code: str = "upstream_ai_error") -> None:
        """Create the error.

        Args:
            message: What to tell the player, in the voice of the application
                rather than the voice of a Google error page.
            code: The machine-readable code, so the frontend can distinguish
                "out of quota" from "the model refused this content".
        """
        super().__init__(status_code=status.HTTP_502_BAD_GATEWAY, code=code, message=message)


class QuotaExhaustedError(ApiError):
    """Raised when the Gemini free tier's allowance is used up."""

    def __init__(self, retry_after_seconds: int = 60) -> None:
        """Create the error.

        Args:
            retry_after_seconds: A suggested wait. Gemini's per-minute limits
                usually clear quickly; a daily limit will not, which is why the
                message mentions both possibilities.
        """
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="ai_quota_exhausted",
            message=(
                "The Dungeon Master needs a moment — the free AI allowance has been used "
                "up. Per-minute limits clear within about a minute; if this persists, the "
                "daily allowance is spent and will reset tomorrow."
            ),
            headers={"Retry-After": str(retry_after_seconds)},
        )


class NotFoundError(ApiError):
    """Raised when a resource does not exist, or the caller may not see it.

    Deliberately does not distinguish "does not exist" from "exists but is
    someone else's". Returning 403 for the second case would confirm that a
    given identifier is real, which is a small information leak available to
    anyone who can guess identifiers.
    """

    def __init__(self, what: str = "resource") -> None:
        """Create the error.

        Args:
            what: The kind of thing not found, e.g. ``"campaign"``. A type
                name only — never an identifier or a title.
        """
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message=f"That {what} could not be found.",
        )


class AuthenticationError(ApiError):
    """Raised on any failed authentication, with a deliberately uniform message."""

    def __init__(self) -> None:
        """Create the error with the single approved wording."""
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="invalid_credentials",
            # Identical whether the account exists, the password is wrong, or
            # the account is suspended. Anything more specific is a map of who
            # is registered.
            message="Those credentials were not recognised.",
        )


class XsrfError(ApiError):
    """Raised when the cross-site request forgery token is missing or wrong."""

    def __init__(self, detail: str) -> None:
        """Create the error.

        Args:
            detail: Which specific check failed. Safe to reveal: an attacker
                already knows they do not have the token, and a developer
                wiring up the frontend needs this to be specific or they will
                lose an afternoon.
        """
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            code="xsrf_failed",
            message=f"Request rejected by cross-site request forgery protection: {detail}",
        )


def _envelope(code: str, message: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the standard error body.

    Args:
        code: The machine-readable code.
        message: The human-readable explanation.
        extra: Any additional safe fields, such as validation field names.

    Returns:
        The response body. Always the same shape, so the frontend has exactly
        one error format to handle.
    """
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "correlation_id": get_correlation_id(),
        }
    }
    if extra:
        body["error"].update(extra)
    return body


async def api_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Turn an ApiError into an HTTP response.

    Args:
        _request: The incoming request, unused.
        exc: The raised error.

    Returns:
        A JSON response in the standard envelope.
    """
    assert isinstance(exc, ApiError)  # noqa: S101 - registered only for ApiError
    _log.info("api_error", reason_code=exc.code, status_code=exc.status_code)
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(exc.code, exc.message),
        headers=exc.headers,
    )


async def validation_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Turn a request-validation failure into a safe response.

    FastAPI's default validation error helpfully includes the value that failed
    validation. That is exactly wrong here: a malformed email address would be
    echoed back and, worse, written to the logs. This handler reports **which
    field** failed and **why**, and never what was in it.

    Args:
        _request: The incoming request, unused.
        exc: The validation error raised by FastAPI.

    Returns:
        A JSON response listing field names and problem types only.
    """
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    fields = [
        {
            # e.g. "body.email" — the location, not the contents.
            "field": ".".join(str(part) for part in error.get("loc", ())),
            "problem": error.get("type", "invalid"),
        }
        for error in exc.errors()
    ]
    _log.info("validation_failed", count=len(fields))
    return JSONResponse(
        status_code=422,  # Unprocessable Content
        content=_envelope(
            "validation_failed",
            "Some of the submitted values were not acceptable.",
            {"fields": fields},
        ),
    )


async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Catch anything unexpected without revealing how the server works.

    The full exception, with its stack trace, goes to the logs where it is
    tagged with the correlation identifier. The browser gets a generic message
    and that same identifier. A user reporting "I saw error a71b-..." gives you
    everything you need.

    Args:
        _request: The incoming request, unused.
        exc: Whatever was raised.

    Returns:
        A generic 500 response carrying only the correlation identifier.
    """
    _log.error("unhandled_exception", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_envelope(
            "internal_error",
            "Something went wrong on our side. Quote the correlation ID below if you "
            "report this.",
        ),
    )
