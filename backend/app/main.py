"""The application itself: assembles everything and starts serving.

WHAT THIS FILE DOES, IN ORDER
1. Reads and validates configuration, refusing to start if anything is unsafe.
2. Builds every long-lived object once — encryption, the AI client, the
   repositories — and stores them where endpoints can reach them.
3. Wraps the application in middleware, in a specific order that matters.
4. Registers the error handlers so that no failure ever leaks internals.
5. Serves.

WHY THE MIDDLEWARE ORDER IS NOT ARBITRARY
Middleware nests like layers of an onion. A request travels inward through each
layer and the reply travels back outward through them in reverse. The order
here is, from outermost to innermost:

    CORS  →  Correlation  →  Security headers  →  XSRF  →  the endpoint

- **CORS is outermost** so that even a rejected request comes back with the
  headers the browser needs in order to *read* the rejection. Without this, a
  403 from the XSRF layer would appear in the browser as an opaque network
  error with no explanation, which is a genuinely miserable thing to debug.
- **Correlation is next** so that every log line produced by anything further
  in — including an XSRF rejection — carries the request's identifier.
- **Security headers sit outside XSRF** so they are attached to error responses
  too, not only to successful ones.
- **XSRF is innermost** of the four, immediately before the endpoint, because
  it is the last gate.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import Container
from app.api.docs import swagger_page
from app.api.v1 import health
from app.api.v1.router import api_router
from app.config import Settings, get_settings
from app.core.errors import (
    ApiError,
    api_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from app.core.logging import configure_logging, get_logger
from app.core.ratelimit import InMemoryRateLimiter
from app.middleware.correlation import CORRELATION_HEADER, CorrelationMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.xsrf import XsrfMiddleware
from app.repositories.memory import (
    MemoryCampaignRepository,
    MemoryCharacterRepository,
    MemorySessionRepository,
    MemoryStore,
    MemoryUserRepository,
)
from app.services.analytics import AnalyticsService
from app.services.auth import AuthService, ensure_demo_user
from app.services.game import GameService
from app.services.gemini import GeminiClient
from app.services.transcription import TranscriptionService

_log = get_logger("startup")

API_DESCRIPTION = """
The backend for an AI Dungeon Master: a Dungeon Master you can talk to, for
people who want to play Dungeons & Dragons without a human running the game.

### What this service does
Receives what a player types or says, asks Google Gemini for the Dungeon
Master's reply in character, and stores the conversation encrypted.

### What it deliberately does not do
* **The AI key never reaches the browser.** Every model call happens here.
* **Audio never leaves this server.** Voice input is transcribed locally rather
  than through the browser's built-in speech recognition, which sends raw audio
  to Google. See ADR-008.
* **Personal data is never stored in plaintext.** Email addresses, names,
  transcripts and anything else a player typed are encrypted with a key unique
  to that player. Deleting an account destroys the key, which makes their data
  unreadable everywhere — including in backups.
* **Logs contain no personal data.** Fields are censored unless explicitly
  declared safe to log.

### Phase 1 limitations
This build runs entirely on one machine with no database.

* **Authentication is stubbed.** Registration and password checking are real,
  but session tokens are placeholders that are not verified. A request with no
  token is treated as the demo account.
* **Storage is in memory.** Everything is lost when the server restarts.

The application refuses to start with either of those settings when
`APP_ENV=production`.
"""


def build_container(settings: Settings) -> Container:
    """Create every long-lived object the application needs.

    Built once at startup rather than per request. The encryption service in
    particular holds a short-lived cache of unwrapped keys, which would be
    useless if it were rebuilt for every request.

    Args:
        settings: The validated application settings.

    Returns:
        The assembled container.
    """
    # Which storage to use is a single configuration choice. Both sets of
    # repositories satisfy the same interfaces in repositories/base.py, so
    # nothing below this point knows or cares which one it got.
    if settings.repository_backend == "mysql":
        from app.repositories.sql import (
            SqlCampaignRepository,
            SqlCharacterRepository,
            SqlSessionRepository,
            SqlStore,
            SqlUserRepository,
        )

        store: Any = SqlStore(settings)
        users: Any = SqlUserRepository(store)
        campaigns: Any = SqlCampaignRepository(store)
        characters: Any = SqlCharacterRepository(store)
        sessions: Any = SqlSessionRepository(store)
    else:
        store = MemoryStore()
        users = MemoryUserRepository(store)
        campaigns = MemoryCampaignRepository(store)
        characters = MemoryCharacterRepository(store)
        sessions = MemorySessionRepository(store)

    analytics = AnalyticsService()
    gemini = GeminiClient(settings)
    transcription = TranscriptionService(settings)
    auth = AuthService(users)

    game = GameService(
        campaigns=campaigns,
        characters=characters,
        sessions=sessions,
        gemini=gemini,
        analytics=analytics,
        scrub_outbound=settings.scrub_outbound_prompts,
    )

    return Container(
        settings=settings,
        store=store,
        limiter=InMemoryRateLimiter(),
        users=users,
        campaigns=campaigns,
        characters=characters,
        sessions=sessions,
        analytics=analytics,
        gemini=gemini,
        transcription=transcription,
        auth=auth,
        game=game,
    )


def _warn_about_development_settings(settings: Settings) -> None:
    """Print a prominent warning when insecure development settings are active.

    Configuration validation already refuses these in production. This warning
    is for the case that actually causes accidents: someone running locally,
    forgetting which mode they are in, and pointing it at something real.

    Args:
        settings: The validated application settings.
    """
    warnings: list[str] = []
    if settings.auth_mode == "stub":
        warnings.append("authentication is stubbed and tokens are not verified")
    if settings.repository_backend == "memory":
        warnings.append("storage is in memory and is lost on restart")

    if not warnings:
        return

    border = "!" * 74
    lines = "\n".join(f"!!  - {warning}" for warning in warnings)
    print(  # noqa: T201 - deliberately bypasses the logger so it cannot be filtered out
        f"\n{border}\n"
        "!!  DEVELOPMENT MODE — NOT SECURE\n!!\n"
        f"{lines}\n!!\n"
        "!!  This is correct for local work. Never point this configuration at\n"
        "!!  real users' data. See docs/SECURITY.md.\n"
        f"{border}\n"
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run startup and shutdown work around the life of the server.

    Args:
        app: The application, so the container can be attached to it.

    Yields:
        Control to the running server. Everything after the ``yield`` runs at
        shutdown.
    """
    settings = get_settings()
    configure_logging(settings)
    _warn_about_development_settings(settings)

    container = build_container(settings)
    app.state.container = container

    # Phase 1 keeps everything in memory, so the demo account has to be
    # recreated on every start. This is what lets the frontend work
    # immediately, without anyone having to register first.
    await ensure_demo_user(container.users)

    _log.info(
        "application_started",
        app_env=settings.app_env,
        repository_backend=settings.repository_backend,
        model_id=settings.gemini_model_id,
        stt_enabled=settings.stt_enabled,
        cors_origins=len(settings.cors_origin_list),
    )

    yield

    await container.gemini.aclose()
    # Close database connections cleanly, if there are any. Without this the
    # server can hang for a few seconds on shutdown waiting for the pool.
    closer = getattr(container.store, "close", None)
    if closer is not None:
        await closer()
    _log.info("application_stopped")


def create_app() -> FastAPI:
    """Build the FastAPI application.

    A function rather than a module-level object so that tests can build a
    second, differently-configured application without restarting the process.

    Returns:
        The configured application.
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=API_DESCRIPTION,
        lifespan=lifespan,
        # The browsable documentation is built from the same Pydantic models
        # that validate every request, so it cannot drift away from what the
        # code actually does.
        #
        # `docs_url=None` switches off FastAPI's stock Swagger page, which is
        # replaced below by one that understands cross-site request forgery
        # tokens. Without that, every "Try it out" on a POST would be refused.
        docs_url=None,
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # --- Middleware. Added innermost first; the LAST added is outermost. ---
    app.add_middleware(XsrfMiddleware, settings=settings)
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(CorrelationMiddleware)
    app.add_middleware(
        CORSMiddleware,
        # Exact origins from configuration. Never a wildcard: the settings
        # validator refuses one, because a wildcard combined with cookies is
        # both a security hole and something browsers reject anyway.
        allow_origins=settings.cors_origin_list,
        # Required so the browser sends the XSRF cookie with its requests.
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", settings.xsrf_header_name, CORRELATION_HEADER],
        # Lets the frontend read the correlation identifier off the response,
        # so it can show it on an error screen. Headers are hidden from
        # cross-origin JavaScript unless they are named here.
        expose_headers=[CORRELATION_HEADER],
        max_age=600,
    )

    # --- Error handlers. Registered so no failure escapes unshaped. ---
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    # --- Documentation ---
    @app.get("/docs", include_in_schema=False)
    async def docs() -> Any:
        """Serve the Swagger page that attaches the XSRF token automatically.

        Returns:
            The documentation page. See ``app/api/docs.py`` for why this
            replaces FastAPI's built-in one.
        """
        return swagger_page(settings.app_name, app.openapi_url or "/openapi.json")

    # --- Routes ---
    app.include_router(health.router)
    app.include_router(api_router)

    return app


app = create_app()
