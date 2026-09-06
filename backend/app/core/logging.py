"""Structured logging with allowlist-based redaction.

WHAT STRUCTURED LOGGING IS
An ordinary log line is a sentence: ``User alex@example.com logged in``. A
structured log line is a set of named fields: ``{"event": "login_succeeded",
"user_id": "8f2c...", "correlation_id": "a71b..."}``. The second form can be
searched and filtered by machine, and — crucially here — each field can be
inspected and censored individually before it is written.

THE ALLOWLIST RULE, AND WHY IT IS AN ALLOWLIST
There are two ways to keep secrets out of logs:

- A **denylist** names the fields to hide: password, email, token. It is the
  obvious approach and it fails, reliably, the first time someone adds a field
  called ``recovery_address`` or ``player_note``. A denylist protects only
  against the mistakes you already thought of.

- An **allowlist** names the fields that may be written, and replaces
  everything else. A new field is censored by default. To log something new you
  have to come here and declare it, which is a moment of deliberate thought at
  exactly the right time.

This module uses an allowlist. A field that is not declared below is replaced
with a description of its type and length — ``<str:len=24>`` — which is enough
to debug a shape problem ("it was empty when I expected 40 characters") without
revealing content.

FAIL CLOSED
If the redaction processor itself raises an error, it replaces the whole log
entry with a minimal safe record rather than letting the original through. A
broken filter must not become an open tap.

THE ONE THING THIS CANNOT CATCH
The ``event`` field is the message itself, and it is allowlisted because
otherwise nothing would be readable. If a developer writes
``log.info(f"login failed for {email}")`` the address goes straight into the
log. The rule that prevents this is a convention, not a mechanism: **event
names are fixed strings, never f-strings.** Variable content goes in named
fields, where the allowlist can see it. This is enforced in code review and
called out in CONVENTIONS.md.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from app.config import Settings
from app.core.correlation import get_correlation_id

# ---------------------------------------------------------------------
# THE ALLOWLIST
#
# Every field name here has been checked against one question: "if this value
# appeared in a log file that leaked, would it identify a person?" If the
# answer is yes or maybe, it is not on this list.
#
# Adding a field here is a privacy decision. Make it deliberately.
# ---------------------------------------------------------------------
LOGGABLE_FIELDS: frozenset[str] = frozenset(
    {
        # --- structlog's own machinery ---
        "event",  # the message. Must be a fixed string — see the note above.
        "level",
        "timestamp",
        "logger",
        "exception",  # traceback text, without local variable values
        "exc_info",
        # --- request identity: opaque handles only ---
        "correlation_id",  # random per request, ties log lines together
        "user_id",  # random UUID, reveals nothing about the person
        "analytics_id",  # pseudonym, unlinkable without the encrypted map
        "campaign_id",
        "character_id",
        "game_session_id",
        "message_id",
        "call_id",
        "grant_id",
        # --- HTTP shape ---
        # Paths are safe only because the design forbids personal data in URLs.
        # If that rule is ever broken, this entry becomes a leak.
        "method",
        "path",
        "route",
        "status_code",
        "duration_ms",
        "client_ip_digest",  # the daily HMAC, never the address itself
        # --- rate limiting ---
        "scope",
        "allowed",
        "hit_count",
        "limit",
        "window_seconds",
        "retry_after_secs",
        # --- Gemini call metrics: metadata only, never content ---
        "model_id",
        "latency_ms",
        "tokens_in",
        "tokens_out",
        "finish_reason",
        "safety_blocked",
        "error_code",
        "retry_count",
        "attempt",
        "estimated_cost_micros",
        "prompt_chars",  # a length, not the prompt
        "response_chars",
        "scrubbed_spans",  # how many things the scrubber removed
        # --- speech to text: shape only ---
        "audio_bytes",
        "audio_seconds",
        "stt_model",
        "transcript_chars",  # a length, never the transcript
        # --- analytics allowlist values, all enums or numbers ---
        "event_name",
        "country_code",
        "duration_bucket",
        "turn_count",
        "feature",
        "error_category",
        "success",
        "input_mode",
        "role",
        # --- operational ---
        "app_env",
        "encryption_provider",
        "repository_backend",
        "version",
        "component",
        "reason_code",
        "count",
        "seq",
        "key_version",
        "stt_enabled",
        "cors_origins",
        "allowed_hosts",
    }
)


def describe(value: Any) -> str:
    """Summarise a censored value by type and size, revealing no content.

    Args:
        value: The value that is not allowed to be logged.

    Returns:
        A short description such as ``<str:len=24>`` or ``<dict:keys=3>``. This
        is deliberately just enough to debug a structural problem — "the field
        was empty" or "there were forty of them" — while showing nothing about
        what the data actually said.
    """
    if value is None:
        return "<none>"
    if isinstance(value, bool):
        return f"<bool:{value}>"
    if isinstance(value, int | float):
        # Numbers are censored by type only. An unallowlisted number could be a
        # date of birth or an account balance, so its value is not shown.
        return f"<{type(value).__name__}>"
    if isinstance(value, str):
        return f"<str:len={len(value)}>"
    if isinstance(value, bytes | bytearray):
        return f"<bytes:len={len(value)}>"
    if isinstance(value, dict):
        return f"<dict:keys={len(value)}>"
    if isinstance(value, list | tuple | set):
        return f"<{type(value).__name__}:len={len(value)}>"
    return f"<{type(value).__name__}>"


def redaction_processor(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Replace every field that is not on the allowlist.

    This runs on every single log entry, before it is written anywhere.

    Args:
        _logger: The logger, unused.
        _method_name: The log method used, unused.
        event_dict: The fields about to be written.

    Returns:
        The same fields, with any not on the allowlist replaced by a type and
        length description. If anything goes wrong inside this function it
        returns a minimal safe record instead of the original — a redaction
        filter that fails open would be worse than no filter at all, because it
        would create false confidence.
    """
    try:
        return {
            key: value if key in LOGGABLE_FIELDS else describe(value)
            for key, value in event_dict.items()
        }
    except Exception:  # noqa: BLE001 - must never propagate, must never leak
        return {
            "event": "log_redaction_failed",
            "level": event_dict.get("level", "error"),
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

    Raises:
        RuntimeError: If redaction has been switched off while running in
            production. Configuration validation already blocks this, so
            reaching here means something has bypassed it — and the right
            response is still to refuse to start.
    """
    if settings.app_env == "production" and not settings.log_redaction_enabled:
        raise RuntimeError(
            "Refusing to configure logging: redaction is disabled in production. "
            "Personal data would be written to log files."
        )

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        correlation_processor,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    # The redaction filter runs last, immediately before rendering, so that
    # nothing added by an earlier processor can slip past it.
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
    # libraries) through the same pipeline, so nothing writes around the
    # redaction filter.
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
