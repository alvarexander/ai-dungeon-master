"""Correlation identifiers: the thread that ties one request's logs together.

WHY THIS EXISTS
When a player reports "the Dungeon Master stopped replying", you need to find
what happened. In a design that forbids reading their data, the usual approach
— look up their account and inspect their records — is unavailable.

So every request is given a random identifier when it arrives. That identifier
is stamped on every log line the request produces, returned to the browser in a
response header, and shown on the error screen. The player reads it to you, you
search for it, and you see the entire life of that one request without ever
touching their personal data.

This is the primary debugging workflow for this application, not a fallback.

HOW THE VALUE TRAVELS
Python's `contextvars` gives each concurrent task its own copy of a variable.
Because the server handles many requests at once, a plain global variable would
be overwritten constantly; a context variable is naturally scoped to the
request that set it, even with hundreds in flight.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

# The identifier for the request currently being handled. Empty outside a
# request, for example in a startup routine or a scheduled job.
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def new_correlation_id() -> str:
    """Create a fresh identifier for an incoming request.

    Returns:
        A random UUID as text. Random and opaque on purpose: it must reveal
        nothing about the user, the time, or the server that produced it.
    """
    return str(uuid.uuid4())


def set_correlation_id(value: str) -> None:
    """Record the identifier for the request being handled right now.

    Args:
        value: The identifier to attach to everything this request does.
    """
    _correlation_id.set(value)


def get_correlation_id() -> str:
    """Read the identifier for the current request.

    Returns:
        The current request's identifier, or an empty string if called outside
        a request.
    """
    return _correlation_id.get()
