"""Middleware that gives every request an identifier and times it.

WHAT MIDDLEWARE IS
Code that runs around every request, before the endpoint sees it and after the
endpoint has produced a reply. Think of it as the front desk of a building:
everyone passes through on the way in and on the way out, so it is the right
place for anything that must happen universally — logging, timing, security
checks — rather than being repeated in every endpoint and eventually forgotten
in one.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.correlation import get_correlation_id, new_correlation_id, set_correlation_id
from app.core.logging import get_logger

_log = get_logger("http")

# The header the identifier is returned in. The frontend reads it and shows it
# on error screens so a user can quote it when reporting a problem.
CORRELATION_HEADER = "X-Correlation-ID"


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Assigns a correlation identifier, logs the request, and returns the ID."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Handle one request from start to finish.

        Args:
            request: The incoming request.
            call_next: Runs the rest of the application and returns its reply.

        Returns:
            The reply, with the correlation identifier added as a header.
        """
        # A client may supply its own identifier so a single user action can be
        # traced across several requests. It is deliberately NOT trusted as-is:
        # an attacker could otherwise send a chosen value and cause log lines
        # to be attributed to someone else's trace, or inject characters that
        # break log parsing. It is accepted only if it is short and consists of
        # safe characters; otherwise a fresh one is generated.
        supplied = request.headers.get(CORRELATION_HEADER, "")
        if supplied and len(supplied) <= 64 and supplied.replace("-", "").isalnum():
            correlation_id = supplied
        else:
            correlation_id = new_correlation_id()

        set_correlation_id(correlation_id)
        started = time.perf_counter()

        # Note what is logged: the method, the route pattern, and a duration.
        # Not the query string, not the body, not the caller's address. The
        # design forbids personal data in URLs, which is what makes even the
        # path safe to record.
        response = await call_next(request)

        duration_ms = int((time.perf_counter() - started) * 1000)
        _log.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        response.headers[CORRELATION_HEADER] = get_correlation_id()
        return response
