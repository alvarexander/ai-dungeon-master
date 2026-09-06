"""Assembles every version 1 route into a single router.

WHY THE URLS START WITH /api/v1
The ``v1`` is a version number. When a future change would break existing
clients — removing a field, changing what one means — it goes in ``/api/v2``
and ``v1`` keeps working until nothing uses it. Without a version in the URL,
the only way to make a breaking change is to break everyone at once.

Adding it costs five characters now. Retrofitting it costs a coordinated
release across every client.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import account, auth, campaigns, characters, chat, voice

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(chat.router)
api_router.include_router(campaigns.router)
api_router.include_router(characters.router)
api_router.include_router(account.router)
api_router.include_router(voice.router)
