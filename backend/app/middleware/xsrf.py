"""Cross-Site Request Forgery protection, matched to Angular's client behaviour.

WHAT XSRF IS
Cross-Site Request Forgery — also written CSRF — is an attack that abuses the
fact that browsers attach your cookies to a request automatically, no matter
which site caused the request.

Concretely: you are logged in to this application. In another tab you open a
page that an attacker controls. That page silently submits a form to
``https://api.example.com/api/v1/account/delete``. Your browser attaches your
session cookie because it always does. The server sees a perfectly valid,
authenticated request to delete your account, and it has no way to tell that
you did not mean it.

THE DEFENCE: THE DOUBLE-SUBMIT COOKIE
The server generates a random token and puts it in a cookie that JavaScript is
allowed to read. The real frontend reads it and copies it into a request
*header*. The server accepts a state-changing request only when the cookie and
the header match.

Why this works: the attacker's page can *cause* your browser to send the cookie,
but it cannot *read* it — the browser's same-origin policy forbids one site
reading another site's cookies. So the attacker cannot produce the matching
header, and the request is rejected.

The analogy: the cookie is a wristband the venue puts on you, and the header is
being asked to state the number written on it. A pickpocket can see you have a
wristband, but cannot read the number, so cannot answer.

═══════════════════════════════════════════════════════════════════════
THE DEPLOYMENT CATCH — read this before going live
═══════════════════════════════════════════════════════════════════════
The pattern requires the frontend to be able to *read* the cookie this server
sets. A browser only permits that when both are under the same parent domain.

Locally this is free: the Angular app is on ``localhost:4200``, this server is
on ``localhost:8000``, and cookies ignore port numbers — so both are
``localhost`` and share cookies. It simply works.

In production they are different hosts, and it only works if you arrange:

    frontend   https://app.example.com    on Hostinger
    backend    https://api.example.com    on Fly.io
    COOKIE_DOMAIN=.example.com

If the backend is left on a ``*.fly.dev`` address while the frontend is on your
own domain, the browser treats them as unrelated sites, the frontend can never
read the token, and every state-changing request will fail with a 403. This is
not a bug to debug on the day — it is a constraint to design for now, which is
why the setting exists and why this note is long.

═══════════════════════════════════════════════════════════════════════
A SECOND CATCH, ON THE ANGULAR SIDE
═══════════════════════════════════════════════════════════════════════
Angular's built-in XSRF support attaches the header only to *relative* URLs,
because it assumes the API is on the same origin as the app. Since our API is
on a different origin, Angular's default would silently attach nothing. The
frontend therefore also registers a small interceptor that attaches the token
to requests aimed at the configured API origin. See
``frontend/src/app/core/http/xsrf.interceptor.ts``.
"""

from __future__ import annotations

import hmac
import secrets
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import Settings
from app.core.correlation import get_correlation_id
from app.core.logging import get_logger

_log = get_logger("xsrf")

# Methods that only read. By long-standing HTTP convention these must not
# change anything, so they need no token — and they are also how the browser
# first obtains one.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

# Paths that must work before a token exists, or that are not browser-driven.
# Kept as short as possible: every entry is a hole in the protection.
EXEMPT_PATHS = frozenset({"/health", "/health/ready", "/docs", "/redoc", "/openapi.json"})

TOKEN_BYTES = 32


class XsrfMiddleware(BaseHTTPMiddleware):
    """Issues XSRF tokens on safe requests and enforces them on unsafe ones."""

    def __init__(self, app: Callable[..., Awaitable[None]], settings: Settings) -> None:
        """Set up the middleware.

        Args:
            app: The next application in the chain.
            settings: Application settings, supplying the cookie and header
                names and the cookie's domain and security flags.
        """
        super().__init__(app)  # type: ignore[arg-type]
        self._settings = settings

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Check or issue the token for one request.

        Args:
            request: The incoming request.
            call_next: Runs the rest of the application.

        Returns:
            Either the normal reply with a token cookie attached, or a 403 if
            the check failed.
        """
        settings = self._settings
        cookie_token = request.cookies.get(settings.xsrf_cookie_name, "")

        needs_check = (
            request.method not in SAFE_METHODS and request.url.path not in EXEMPT_PATHS
        )

        if needs_check:
            header_token = request.headers.get(settings.xsrf_header_name, "")
            failure = self._check(cookie_token, header_token)
            if failure is not None:
                _log.warning(
                    "xsrf_rejected",
                    method=request.method,
                    path=request.url.path,
                    reason_code=failure,
                )
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": {
                            "code": "xsrf_failed",
                            "message": (
                                "Request rejected by cross-site request forgery protection. "
                                "Reload the page and try again."
                            ),
                            "correlation_id": get_correlation_id(),
                        }
                    },
                )

        response = await call_next(request)

        # Make sure the browser always ends up holding a token. Issued on the
        # first request that does not already have one, so the very first
        # page load leaves the app ready to make a state-changing request.
        if not cookie_token:
            self._issue(response)

        return response

    @staticmethod
    def _check(cookie_token: str, header_token: str) -> str | None:
        """Compare the cookie and header tokens.

        Args:
            cookie_token: The value from the cookie.
            header_token: The value echoed back in the header.

        Returns:
            ``None`` if the request is acceptable, otherwise a short code
            naming which check failed. The codes are for the log; the user
            always sees the same generic message.
        """
        if not cookie_token:
            return "missing_cookie"
        if not header_token:
            return "missing_header"
        # A constant-time comparison. An ordinary ``==`` stops at the first
        # differing character, so the time it takes leaks how much of the token
        # was guessed correctly — enough, in principle, to recover it one
        # character at a time.
        if not hmac.compare_digest(cookie_token, header_token):
            return "mismatch"
        return None

    def _issue(self, response: Response) -> None:
        """Attach a freshly generated token cookie to a response.

        Args:
            response: The response to attach the cookie to.
        """
        settings = self._settings
        response.set_cookie(
            key=settings.xsrf_cookie_name,
            value=secrets.token_urlsafe(TOKEN_BYTES),
            # MUST be readable by JavaScript. This is the one cookie in the
            # application that is deliberately not httponly, because the whole
            # mechanism depends on the frontend reading it and echoing it back.
            # It is safe: the token is not a credential — knowing it grants
            # nothing without also holding the session.
            httponly=False,
            secure=settings.cookie_secure,
            # "lax" allows the cookie on same-site requests, which includes
            # app.example.com calling api.example.com, while blocking it on
            # genuinely cross-site form submissions — the attack above.
            samesite="lax",
            domain=settings.cookie_domain or None,
            path="/",
            max_age=60 * 60 * 12,
        )
