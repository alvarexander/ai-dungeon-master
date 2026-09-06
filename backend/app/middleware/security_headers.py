"""Response headers that instruct the browser to defend the user.

Browsers implement a set of protections that are switched *off* unless the
server asks for them. Each header below is one such request. They cost nothing
and close whole categories of attack, so they are applied to every response.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import Settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds a standard set of protective headers to every response."""

    def __init__(self, app: Callable[..., Awaitable[None]], settings: Settings) -> None:
        """Set up the middleware.

        Args:
            app: The next application in the chain.
            settings: Application settings; HSTS is only sent in production,
                since it would break local development over plain HTTP.
        """
        super().__init__(app)  # type: ignore[arg-type]
        self._settings = settings

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Add the headers to one response.

        Args:
            request: The incoming request.
            call_next: Runs the rest of the application.

        Returns:
            The response with security headers attached.
        """
        response = await call_next(request)
        headers = response.headers

        # Stops the browser second-guessing the declared content type. Without
        # it, a browser can decide a file we called JSON "looks like" HTML and
        # run it as a page — which turns an uploaded file into a script.
        headers["X-Content-Type-Options"] = "nosniff"

        # Refuses to let this API be displayed inside a frame on another site,
        # which defeats clickjacking (invisible frames overlaid on a decoy
        # page so that a click lands somewhere the user cannot see).
        headers["X-Frame-Options"] = "DENY"

        # Stops the full URL of our pages being sent to sites we link to.
        headers["Referrer-Policy"] = "no-referrer"

        # Switches off browser features this API has no use for. If an attacker
        # ever did manage to run code in a response from this origin, they
        # still could not reach the microphone or camera through it.
        headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=(), payment=()"

        # This API returns JSON, never a page. The strictest possible content
        # policy is therefore free: nothing is permitted to load at all.
        # The Swagger documentation pages are exempt because they legitimately
        # load styles and scripts to render themselves.
        if not request.url.path.startswith(("/docs", "/redoc", "/openapi.json")):
            headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"

        # HSTS (HTTP Strict Transport Security) tells the browser to refuse
        # plain HTTP to this host from now on, for two years. Only sent in
        # production: sending it locally would make the browser refuse to talk
        # to localhost over HTTP, which is difficult to undo and would break
        # every other project on the machine.
        if self._settings.app_env == "production":
            headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"

        return response
