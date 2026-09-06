"""Structured logging, with sensitive values kept out of the log.

WHAT STRUCTURED LOGGING IS
An ordinary log line is a sentence: ``User alex@example.com logged in``. A
structured log line is a set of named fields: ``{"event": "login_succeeded",
"user_id": "8f2c...", "correlation_id": "a71b..."}``. The second form can be
searched and filtered by machine — and each field can be inspected before it is
written.

WHAT IS KEPT OUT
Passwords, tokens, API keys and anything else obviously secret. Those are
replaced with ``<redacted>`` wherever they appear, because a log file is copied,
shipped to other services, and read by people — it is the wrong place for a
credential even briefly.

Request bodies are never logged at all. The request line, the status code and
the duration are, and those are enough to see what happened.

WHAT IS NOT KEPT OUT, AND WHY THAT IS A CHOICE
Email addresses and message content are not automatically stripped. If you
deliberately log one, it will appear. That keeps the logging simple to work
with — you can log what you need while debugging without editing a list first.

The practical rule that replaces it: **log identifiers, not contents.** A
`user_id` tells you which account without putting anybody's details in a file
that gets copied around. Every log call in this codebase follows that rule, and
new ones should too.

THE CONVENTION THAT MATTERS MOST
Event names are fixed strings, and variable content goes in named fields:

    log.info("login_failed", user_id=str(user_id))     # right
    log.info(f"login failed for {email}")               # wrong

The second form bakes the address into the message itself, where nothing can
inspect it. It is also much harder to search, because every line is different.
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog

from app.config import Settings
from app.core.correlation import get_correlation_id

# Words that make a field a credential. A field name is split into words and
# matched against this set, rather than being searched for substrings.
#
# The distinction is not pedantry. A naive substring check on "token" also
# matches `tokens_in` — the count of tokens in an AI prompt — and would quietly
# redact the numbers the whole observability story depends on. It fails
# silently and looks like the filter working, which is the worst kind of bug.
SENSITIVE_WORDS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "authorization",
        "cookie",
        "credential",
        "credentials",
        "passphrase",
    }
)

# Compound names that do not split into a sensitive word on their own.
SENSITIVE_PHRASES: tuple[str, ...] = ("api_key", "apikey", "private_key", "auth_header")

REDACTED = "<redacted>"


def _words(field_name: str) -> set[str]:
    """Split a field name into its component words.

    Handles ``snake_case``, ``kebab-case`` and ``camelCase`` alike, so that
    ``accessToken``, ``access_token`` and ``Access-Token`` all yield the same
    words.

    Args:
        field_name: The field name.

    Returns:
        The lowercased words it is made of.
    """
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", field_name)
    return {part for part in re.split(r"[^A-Za-z0-9]+", spaced.lower()) if part}


def is_sensitive(field_name: str) -> bool:
    """Report whether a field's value must be kept out of the log.

    Args:
        field_name: The name of the field about to be written.

    Returns:
        True if the name looks like a credential.
    """
    lowered = field_name.lower()
    if any(phrase in lowered for phrase in SENSITIVE_PHRASES):
        return True
    return bool(_words(field_name) & SENSITIVE_WORDS)


def redaction_processor(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Replace the value of any field whose name looks like a credential.

    Runs on every log entry, before it is written anywhere.

    Args:
        _logger: The logger, unused.
        _method_name: The log method used, unused.
        event_dict: The fields about to be written.

    Returns:
        The same fields, with sensitive values replaced. If anything goes wrong
        inside this function it returns a minimal record instead of the
        original — a filter that failed open would be worse than no filter,
        because it would create confidence that is not warranted.
    """
    try:
        return {
            key: REDACTED if is_sensitive(key) else value for key, value in event_dict.items()
        }
    except Exception:  # noqa: BLE001 - must never propagate, must never leak
        return {
            "event": "log_redaction_failed",
            "level": "error",
            "correlation_id": get_correlation_id(),
        }


def correlation_processor(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Stamp the current request's correlation identifier on every log entry.

    Args:
        _logger: The logger, unused.
        _method_name: The log method used, unused.
        event_dict: The fields about to be written.

    Returns:
        The fields with ``correlation_id`` added, when inside a request.
    """
    correlation_id = get_correlation_id()
    if correlation_id:
        event_dict["correlation_id"] = correlation_id
    return event_dict


def configure_logging(settings: Settings) -> None:
    """Set up logging for the whole process. Call once, at startup.

    Args:
        settings: The application settings. ``log_format`` chooses between
            human-readable console output for local work and one JSON object
            per line for production, where a machine reads it.
    """
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        correlation_processor,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    # The redaction filter runs last, immediately before rendering, so nothing
    # added by an earlier processor can slip past it.
    if settings.log_redaction_enabled:
        processors.append(redaction_processor)

    if settings.log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Route the standard library's logging (used by uvicorn and third-party
    # libraries) through the same pipeline, so nothing writes around the filter.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
    )


def get_logger(component: str) -> Any:
    """Get a logger tagged with which part of the application is speaking.

    Args:
        component: A short name such as ``"gemini"`` or ``"ratelimit"``.

    Returns:
        A bound structlog logger.
    """
    return structlog.get_logger().bind(component=component)
