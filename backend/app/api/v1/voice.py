"""Speech to text. Audio is transcribed on this server and never sent onward."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.deps import ContainerDep, CurrentUser, rate_limit
from app.schemas.common import ErrorResponse
from app.schemas.voice import TranscriptionResponse

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post(
    "/transcribe",
    response_model=TranscriptionResponse,
    responses={
        413: {"model": ErrorResponse, "description": "The recording is too large or too long."},
        415: {"model": ErrorResponse, "description": "Unsupported audio format."},
        422: {"model": ErrorResponse, "description": "The recording could not be read."},
        503: {"model": ErrorResponse, "description": "Speech-to-text is not available."},
    },
    dependencies=[Depends(rate_limit("stt"))],
    summary="Turn a recording into text",
)
async def transcribe(
    container: ContainerDep,
    _user: CurrentUser,
    audio: UploadFile = File(  # noqa: B008 - FastAPI's declaration style
        description="The recording, as captured by the browser. Usually WebM/Opus."
    ),
) -> TranscriptionResponse:
    """Transcribe an uploaded recording, entirely on this server.

    **The audio does not leave this machine.** It is transcribed in memory by a
    local model, and the bytes are discarded when this function returns. They
    are never written to disk, never sent to Google, and never logged.

    That is the reason this endpoint exists rather than using the browser's
    built-in speech recognition, which in Chrome streams the raw microphone
    audio to Google's servers — placing a recording of the user's voice, and
    whatever else is audible in their room, outside the boundary this whole
    design maintains. See ADR-008 for the cost of that decision.

    Rate limited to ten recordings per minute. Transcription is the most
    processor-intensive thing this server does, so this limit protects the
    machine's responsiveness as much as it prevents abuse.

    Args:
        container: The application container.
        _user: The account making the request. Required so that anonymous
            callers cannot use the server as a free transcription service.
        audio: The uploaded recording.

    Returns:
        The transcript and its metadata.

    Raises:
        ApiError: If the recording is too large, too long, or unreadable.
        TranscriptionUnavailableError: If speech-to-text is switched off or the
            optional libraries are not installed.
    """
    data = await audio.read()
    result = await container.transcription.transcribe(data, audio.content_type)
    return TranscriptionResponse(
        transcript=result.text,
        duration_seconds=round(result.duration_seconds, 2),
        language=result.language,
        model=result.model,
        processed_locally=True,
    )
