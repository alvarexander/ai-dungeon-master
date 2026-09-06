"""Dependency injection: how endpoints obtain the things they need.

WHAT DEPENDENCY INJECTION IS
Instead of each endpoint building its own database connection and its own AI
client, it *declares* what it needs — "give me the current user", "give me the
game service" — and the framework supplies it.

Two reasons this matters beyond tidiness:

1. **Security checks cannot be forgotten.** Rate limiting is a declared
   dependency. An endpoint that declares it is protected; the check runs before
   a single line of the endpoint's body. There is no way to write the endpoint
   and then forget to call the limiter, because calling it is not the
   endpoint's job.
2. **Testing.** A test replaces the real Gemini client with a fake one by
   overriding a single dependency, without touching the endpoint at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Header, Request

from app.config import Settings, get_settings
from app.core.errors import ApiError, RateLimitedError
from app.core.logging import get_logger
from app.core.ratelimit import InMemoryRateLimiter
from app.core.security.blind_index import BlindIndexService
from app.core.security.crypto import EncryptionService
from app.repositories.base import User
from app.repositories.memory import (
    MemoryCampaignRepository,
    MemoryCharacterRepository,
    MemorySessionRepository,
    MemoryStore,
    MemoryUserRepository,
)
from app.services.analytics import AnalyticsService
from app.services.auth import AuthService
from app.services.game import GameService
from app.services.gemini import GeminiClient
from app.services.transcription import TranscriptionService

_log = get_logger("deps")


@dataclass(slots=True)
class Container:
    """Every long-lived object in the application, built once at startup.

    Held on ``app.state`` so that endpoints reach it through the request rather
    than through module-level globals — which makes it possible to run two
    differently-configured applications in one test process.
    """

    settings: Settings
    store: MemoryStore
    encryption: EncryptionService
    blind_index: BlindIndexService
    limiter: InMemoryRateLimiter
    users: MemoryUserRepository
    campaigns: MemoryCampaignRepository
    characters: MemoryCharacterRepository
    sessions: MemorySessionRepository
    analytics: AnalyticsService
    gemini: GeminiClient
    transcription: TranscriptionService
    auth: AuthService
    game: GameService


def get_container(request: Request) -> Container:
    """Fetch the application container from the current request.

    Args:
        request: The incoming request.

    Returns:
        The container built at startup.
    """
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def client_ip(request: Request) -> str:
    """Determine the caller's network address, honouring the edge proxy.

    In production Cloudflare and Fly.io both sit in front of this server, so
    the direct connection comes from them rather than from the player. The real
    address arrives in a header.

    A warning about trusting headers: any caller can *claim* any address by
    setting these headers. That would let an attacker evade rate limiting by
    sending a different fake address each time. It is safe here only because in
    production nothing reaches this server except through Fly.io's proxy, which
    replaces these headers rather than passing them through. If that ever
    stops being true — a direct port opened for debugging, say — rate limiting
    by address becomes bypassable.

    Args:
        request: The incoming request.

    Returns:
        The caller's address, or ``"unknown"`` if it cannot be determined.
    """
    forwarded = request.headers.get("fly-client-ip") or request.headers.get("cf-connecting-ip")
    if forwarded:
        return forwarded.strip()
    chain = request.headers.get("x-forwarded-for")
    if chain:
        # The first entry is the original client; the rest are proxies.
        return chain.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(scope: str) -> Callable[..., Awaitable[None]]:
    """Build a dependency that enforces one named rate limit.

    Used as ``dependencies=[Depends(rate_limit("login"))]`` on an endpoint. The
    check runs before the endpoint body, so an endpoint that declares it cannot
    accidentally skip it.

    Args:
        scope: Which limit to apply — one of the keys in
            ``Settings.rate_limits``.

    Returns:
        A callable to pass to ``Depends``. Returned bare rather than already
        wrapped, so the call site reads ``Depends(rate_limit("login"))`` and it is
        obvious at a glance that the endpoint is protected.
    """

    async def _enforce(request: Request, container: ContainerDep) -> None:
        """Count this request and refuse it if the limit is exceeded.

        Args:
            request: The incoming request.
            container: The application container.

        Raises:
            RateLimitedError: If the caller is over the limit.
        """
        rule = container.settings.rate_limits[scope]
        # The address is fingerprinted before it is used. This is the whole
        # privacy claim about rate limiting: what gets counted is a digest that
        # changes daily, never a readable address.
        bucket = container.blind_index.ip_digest(client_ip(request))
        result = container.limiter.hit(bucket, scope, rule)

        if not result.allowed:
            _log.warning(
                "rate_limit_exceeded",
                scope=scope,
                hit_count=result.hit_count,
                limit=result.limit,
                retry_after_secs=result.retry_after_seconds,
                path=request.url.path,
            )
            raise RateLimitedError(result.retry_after_seconds, scope)

    return _enforce


async def get_current_user(
    container: ContainerDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """Identify who is making the request.

    **PHASE 1 BEHAVIOUR — this is the stubbed part of authentication.** The
    token is not verified, because it is not signed. If no token is supplied at
    all, the demo account is returned so the interface can be explored without
    signing in.

    Both behaviours are unacceptable in production, which is why the
    application refuses to start with ``AUTH_MODE=stub`` when
    ``APP_ENV=production``. See ``app/services/auth.py``.

    Args:
        container: The application container.
        authorization: The ``Authorization`` header, if present.

    Returns:
        The account making the request.

    Raises:
        ApiError: If a token is supplied but is malformed, or names an account
            that does not exist.
    """
    if not authorization:
        demo = await container.users.find_by_username("demo-adventurer")
        if demo is None:
            raise ApiError(
                503,
                "demo_user_missing",
                "The demo account is not available. Restart the server, or run "
                "'uv run python scripts/seed_dev_data.py'.",
            )
        return demo

    token = authorization.removeprefix("Bearer ").strip()
    user_id = container.auth.user_id_from_token(token)
    if user_id is None:
        raise ApiError(401, "invalid_token", "That session token is not valid. Sign in again.")

    user = await container.users.get(user_id)
    if user is None:
        raise ApiError(401, "invalid_token", "That session is no longer valid. Sign in again.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
