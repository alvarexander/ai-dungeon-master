"""Health checks: is the server alive, and is it ready to do work?

WHY THERE ARE TWO
Hosting platforms need to know two different things, and conflating them causes
outages.

- **Liveness** ("/health") asks: is the process running? If this fails, the
  platform restarts the machine.
- **Readiness** ("/health/ready") asks: can it actually serve requests? If this
  fails, the platform stops sending traffic but does *not* restart — because
  restarting will not fix a missing API key.

Getting this wrong produces a machine that restarts forever because its
configuration is wrong, which looks like a crash loop and hides the real cause.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.deps import ContainerDep
from app.core.correlation import get_correlation_id

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness check")
async def health() -> dict[str, str]:
    """Report that the process is running.

    Deliberately does no work: no database call, no AI call. A liveness check
    that depends on an external service will fail when that service has a bad
    minute, and the platform will respond by restarting a perfectly healthy
    machine.

    Returns:
        A minimal acknowledgement.
    """
    return {"status": "ok"}


@router.get("/health/ready", summary="Readiness check")
async def ready(container: ContainerDep) -> dict[str, Any]:
    """Report whether the server is configured well enough to serve requests.

    Args:
        container: The application container.

    Returns:
        A summary of the security-relevant configuration. Every value here is
        an environment name, a boolean, or a count — deliberately nothing that
        could be a secret, since this endpoint is reachable without signing in.
        The ``warnings`` list is what makes it useful: it says out loud when
        the server is running with development shortcuts enabled.
    """
    settings = container.settings
    warnings: list[str] = []

    if settings.auth_mode == "stub":
        warnings.append(
            "Authentication is stubbed. Session tokens are not verified and requests "
            "without a token are treated as the demo account."
        )
    if settings.repository_backend == "memory":
        warnings.append("Storage is in memory. Everything is lost when the server restarts.")
    if not settings.stt_enabled:
        warnings.append("Voice input is switched off in configuration.")

    return {
        "status": "ready",
        "app_env": settings.app_env,
        "repository_backend": settings.repository_backend,
        "auth_mode": settings.auth_mode,
        "model_id": settings.gemini_model_id,
        "stt_enabled": settings.stt_enabled,
        "gemini_key_configured": bool(settings.gemini_api_key.get_secret_value().strip())
        and not settings.gemini_api_key.get_secret_value().startswith("CHANGE_ME"),
        "correlation_id": get_correlation_id(),
        "warnings": warnings,
    }
