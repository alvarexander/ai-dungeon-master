"""Registration, sign-in and sign-out.

PHASE 1 STATUS
Registration and password verification are real. The session token is a
placeholder — see ``app/services/auth.py`` for exactly where the line falls and
why the application refuses to start this way in production.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import ContainerDep, CurrentUser, SettingsDep, rate_limit
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    UserProfile,
    XsrfTokenResponse,
)
from app.schemas.common import Acknowledgement, ErrorResponse

router = APIRouter(prefix="/auth", tags=["authentication"])

_ERRORS = {
    409: {"model": ErrorResponse, "description": "Username or email already in use."},
    422: {"model": ErrorResponse, "description": "The submitted values were not acceptable."},
    429: {"model": ErrorResponse, "description": "Too many attempts."},
}


def _profile(user: object) -> UserProfile:
    """Turn a stored account into the public profile shape.

    Args:
        user: The account, with fields already decrypted.

    Returns:
        The profile as the API returns it.
    """
    return UserProfile(
        user_id=str(user.user_id),  # type: ignore[attr-defined]
        username=user.username,  # type: ignore[attr-defined]
        display_name=user.display_name,  # type: ignore[attr-defined]
        email=user.email,  # type: ignore[attr-defined]
        email_verified=user.email_verified,  # type: ignore[attr-defined]
        created_at=user.created_at.isoformat().replace("+00:00", "Z"),  # type: ignore[attr-defined]
        is_stub=True,
    )


@router.get("/csrf", response_model=XsrfTokenResponse, summary="Obtain a cross-site request forgery token")
async def csrf_token(request: Request, settings: SettingsDep) -> XsrfTokenResponse:
    """Return the cross-site request forgery token for this browser.

    The token is normally delivered as a cookie by middleware, and the frontend
    reads it from there. This endpoint returns the same value in the response
    body as well, for one specific reason: if the frontend and backend end up
    on unrelated domains, the browser silently refuses to let the frontend read
    the cookie, and every later request fails with a confusing 403. Calling
    this at startup turns that silent misconfiguration into a clear diagnostic.

    Args:
        request: The incoming request, carrying the cookie set by middleware.
        settings: Application settings, supplying the cookie and header names.

    Returns:
        The token and the names the frontend must use.
    """
    return XsrfTokenResponse(
        token=request.cookies.get(settings.xsrf_cookie_name, ""),
        header_name=settings.xsrf_header_name,
        cookie_name=settings.xsrf_cookie_name,
    )


@router.post(
    "/register",
    response_model=UserProfile,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    dependencies=[Depends(rate_limit("register"))],
    summary="Create an account",
)
async def register(payload: RegisterRequest, container: ContainerDep) -> UserProfile:
    """Create a new account.

    What genuinely happens: the password is hashed with Argon2id, the email is
    encrypted under a Data Encryption Key minted for this account alone, and a
    keyed fingerprint of the email is stored so that sign-in can find the
    account without the address ever being readable.

    Rate limited more strictly than anything except sign-in, because
    registration is the other endpoint that can be used to discover which email
    addresses already exist.

    Args:
        payload: The validated registration details.
        container: The application container.

    Returns:
        The created account's profile.
    """
    user = await container.auth.register(payload)
    if user.settings.analytics_opt_in:
        container.analytics.record(user.user_id, "signup_completed")
    return _profile(user)


@router.post(
    "/login",
    response_model=LoginResponse,
    responses={401: {"model": ErrorResponse, "description": "Credentials not recognised."}, **_ERRORS},
    dependencies=[Depends(rate_limit("login"))],
    summary="Sign in",
)
async def login(payload: LoginRequest, container: ContainerDep) -> LoginResponse:
    """Verify credentials and return a session token.

    Every failure returns the same 401 with the same wording, whether the
    account does not exist, the password is wrong, or the account is suspended.
    A more helpful message would be a map of who is registered.

    The strictest rate limit in the application applies here: five attempts per
    fifteen minutes. That is what makes password guessing impractical, and it
    is also the mitigation for the one thing the encrypted-email design leaks —
    an attacker able to ask "does this address exist?" thousands of times per
    second could enumerate users, and this stops them at five.

    Args:
        payload: The submitted credentials.
        container: The application container.

    Returns:
        A session token and the account's profile.
    """
    user = await container.auth.authenticate(payload)
    if user.settings.analytics_opt_in:
        container.analytics.record(user.user_id, "login_succeeded", success=True)
    return LoginResponse(
        access_token=container.auth.issue_token(user),
        expires_in=3600,
        user=_profile(user),
        is_stub=True,
    )


@router.post("/logout", response_model=Acknowledgement, summary="Sign out")
async def logout(response: Response, settings: SettingsDep) -> Acknowledgement:
    """Sign out of the current session.

    In Phase 2 this revokes the session in the database. Today it clears the
    cross-site request forgery cookie so the browser starts fresh, and the
    frontend discards its copy of the token.

    Args:
        response: The outgoing response, so the cookie can be cleared.
        settings: Application settings, supplying the cookie name and domain.

    Returns:
        A confirmation.
    """
    response.delete_cookie(
        settings.xsrf_cookie_name, domain=settings.cookie_domain or None, path="/"
    )
    return Acknowledgement(detail="Signed out.")


@router.get("/me", response_model=UserProfile, summary="Who am I?")
async def me(user: CurrentUser) -> UserProfile:
    """Return the signed-in account's profile.

    The email address is decrypted for this one response and is neither cached
    nor logged.

    Args:
        user: The account making the request.

    Returns:
        The profile.
    """
    return _profile(user)
