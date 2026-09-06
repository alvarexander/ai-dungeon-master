"""The conversation with the Dungeon Master. This is the working core of Phase 1."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import ContainerDep, CurrentUser, rate_limit
from app.core.errors import NotFoundError
from app.schemas.chat import (
    ChatTurnRequest,
    ChatTurnResponse,
    DebugCaptureRequest,
    TokenUsage,
    TranscriptMessage,
)
from app.schemas.common import Acknowledgement, ErrorResponse

router = APIRouter(prefix="/chat", tags=["dungeon master"])


def _uuid_or_none(value: str | None, what: str) -> UUID | None:
    """Parse an optional identifier from a request.

    Args:
        value: The text form, or ``None``.
        what: What kind of thing it identifies, for the error message.

    Returns:
        The parsed identifier, or ``None``.

    Raises:
        NotFoundError: If the text is not a valid identifier. Deliberately
            "not found" rather than "malformed": both answers are the same to
            a legitimate client, and treating them identically means a caller
            cannot tell a badly-formed identifier from one that simply is not
            theirs.
    """
    if value is None:
        return None
    try:
        return UUID(value)
    except ValueError as exc:
        raise NotFoundError(what) from exc


@router.post(
    "/turn",
    response_model=ChatTurnResponse,
    responses={
        429: {"model": ErrorResponse, "description": "Rate limited, or the AI allowance is spent."},
        502: {"model": ErrorResponse, "description": "The AI service failed."},
    },
    dependencies=[Depends(rate_limit("chat"))],
    summary="Say something to the Dungeon Master",
)
async def take_turn(
    payload: ChatTurnRequest,
    request: Request,
    user: CurrentUser,
    container: ContainerDep,
) -> ChatTurnResponse:
    """Send one message and receive the Dungeon Master's narration.

    What happens between the request and the reply:

    1. The campaign and play session are found, or created on the first turn.
    2. The recent conversation is loaded and decrypted.
    3. Anything shaped like personal data — an email address, a phone number —
       is stripped from the message before it leaves this server, because
       Google's free tier terms permit them to use prompts for training.
    4. Gemini is called with the Dungeon Master's instructions.
    5. Both messages are stored, encrypted under this user's key.
    6. A pseudonymous analytics event is recorded, carrying no free text.

    Rate limited at twenty turns per minute, which is far above natural play
    and well below what would exhaust a daily AI allowance in one sitting.

    Args:
        payload: The player's message and which conversation it belongs to.
        request: The incoming request, for the country header.
        user: The account making the request.
        container: The application container.

    Returns:
        The narration, the session identifier, and what the turn cost.
    """
    outcome = await container.game.take_turn(
        user=user,
        message_text=payload.message,
        campaign_id=_uuid_or_none(payload.campaign_id, "campaign"),
        session_id=_uuid_or_none(payload.session_id, "session"),
        input_mode=payload.input_mode,
        country_code=container.analytics.country_from_headers(
            {k.lower(): v for k, v in request.headers.items()}
        ),
    )
    return ChatTurnResponse(
        session_id=str(outcome.session.game_session_id),
        message_id=str(outcome.dm_message.message_id),
        reply=outcome.dm_message.content,
        turn=outcome.session.turn_count,
        usage=TokenUsage(
            tokens_in=outcome.tokens_in,
            tokens_out=outcome.tokens_out,
            model_id=outcome.model_id,
            latency_ms=outcome.latency_ms,
        ),
        scrubbed=outcome.scrubbed,
    )


@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[TranscriptMessage],
    summary="Read a conversation",
)
async def list_messages(
    session_id: UUID,
    user: CurrentUser,
    container: ContainerDep,
    after_seq: int = Query(default=0, ge=0, description="Return messages after this position."),
    limit: int = Query(default=50, ge=1, le=200, description="How many to return."),
) -> list[TranscriptMessage]:
    """Read a page of a stored conversation.

    Every message is decrypted here, in memory, for this response only. Paging
    is by position — a plain integer — because the content itself cannot be
    searched or sorted while it is ciphertext.

    The page size is capped at 200 for a privacy reason as well as a
    performance one: each message costs a decryption, so an uncapped request
    would be a way to make the server decrypt an entire campaign at once.

    Args:
        session_id: Which conversation.
        user: The account making the request. Enforced, so guessing a session
            identifier does not reveal someone else's game.
        container: The application container.
        after_seq: Return messages after this position.
        limit: Page size.

    Returns:
        The messages, oldest first.

    Raises:
        NotFoundError: If the session does not exist or is not the caller's.
    """
    session = await container.sessions.get_session(user.user_id, session_id)
    if session is None:
        raise NotFoundError("session")

    messages = await container.sessions.list_messages(
        user.user_id, session_id, after_seq=after_seq, limit=limit
    )
    return [
        TranscriptMessage(
            message_id=str(message.message_id),
            seq=message.seq,
            role=message.role,  # type: ignore[arg-type]
            content=message.content,
            input_mode=message.input_mode,  # type: ignore[arg-type]
            created_at=message.created_at.isoformat().replace("+00:00", "Z"),
        )
        for message in messages
    ]


@router.post(
    "/sessions/{session_id}/debug-capture",
    response_model=Acknowledgement,
    summary="Opt in to storing prompt content for debugging",
)
async def set_debug_capture(
    session_id: UUID,
    payload: DebugCaptureRequest,
    user: CurrentUser,
    container: ContainerDep,
) -> Acknowledgement:
    """Turn the opt-in prompt capture on or off for one session.

    By default, prompt and response *content* is never stored — only metrics
    like token counts and latency. That is the right default, and it means some
    faults are hard to diagnose.

    This is the escape hatch, and it is the player's to open. When switched on,
    the exact prompt and reply are stored encrypted under the player's own key
    for at most 48 hours, and are readable only through the audited support
    flow, which writes an entry into the player's own visible activity log.

    The interface presents this as "help us debug this session", because that
    is precisely what it is.

    Args:
        session_id: Which session.
        payload: Whether to switch capture on or off.
        user: The account making the request.
        container: The application container.

    Returns:
        A confirmation stating what is now true.

    Raises:
        NotFoundError: If the session does not exist or is not the caller's.
    """
    session = await container.sessions.set_debug_capture(user.user_id, session_id, payload.enabled)
    if session is None:
        raise NotFoundError("session")
    detail = (
        "Debug capture is on for this session. Prompt content will be stored, encrypted "
        "with your key, for 48 hours and then deleted automatically."
        if payload.enabled
        else "Debug capture is off. No prompt content will be stored."
    )
    return Acknowledgement(detail=detail)
