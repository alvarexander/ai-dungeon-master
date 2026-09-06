"""Speech-to-text, performed on this server so audio never leaves it.

WHY THIS IS NOT THE BROWSER'S BUILT-IN FEATURE
Browsers have a speech recognition API that would make this file unnecessary.
In Chrome it works by streaming the raw microphone audio to Google's servers.
That would put a recording of the user's voice — in their home, with whoever
else is audible in the room — outside the boundary this design exists to
maintain. No amount of encrypting the database afterwards compensates for
having posted the audio elsewhere first.

So transcription happens here, using faster-whisper: an efficient
implementation of OpenAI's open-source Whisper model that runs on an ordinary
processor with no network access at all. The audio arrives, is transcribed in
memory, and is discarded. It is never written to disk and never leaves.

WHY NOT SEND THE AUDIO TO GEMINI, WHICH WE ALREADY USE?
Google offers a speech model through the same API. It was considered and
rejected for the same reason: it is a third party receiving raw audio.

The honest tension is that we *do* send the transcribed text to Gemini. The two
are not equivalent. Text can be scrubbed of names before it is sent, inspected,
and reasoned about. A voice recording cannot be scrubbed — it carries the
speaker's identity in its waveform regardless of what words are in it. Text is
a controllable leak; audio is not.

WHAT THIS COSTS
Real money. Transcription is computation, and it happens on our server rather
than Google's. The `base` model needs roughly 1 GB of memory, which moves the
Fly.io machine from the smallest size to a 1 GB instance — about five dollars a
month. That is the price of the guarantee, stated plainly.

FIRST RUN IS SLOW
The model weights are downloaded the first time transcription is used —
roughly 145 MB for `base`. This happens once and is then cached on disk. In
production the download happens during the container build, not on the first
player's request.
"""

from __future__ import annotations

import asyncio
import io
import time
from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.core.errors import ApiError
from app.core.logging import get_logger

_log = get_logger("stt")


@dataclass(frozen=True, slots=True)
class Transcription:
    """The result of transcribing one recording.

    Attributes:
        text: What was said.
        duration_seconds: Length of the audio.
        language: Detected language code, such as ``"en"``.
        model: Which model size was used.
    """

    text: str
    duration_seconds: float
    language: str
    model: str


class TranscriptionUnavailableError(ApiError):
    """Raised when speech-to-text is switched off or not installed.

    A distinct, clearly worded error rather than a generic failure, because the
    cause is almost always one specific fixable thing: the optional voice
    dependencies were not installed.
    """

    def __init__(self, detail: str) -> None:
        """Create the error.

        Args:
            detail: What is missing and how to fix it.
        """
        super().__init__(
            status_code=503,
            code="stt_unavailable",
            message=f"Voice input is not available. {detail}",
        )


class TranscriptionService:
    """Loads the speech model on first use and transcribes uploaded audio."""

    def __init__(self, settings: Settings) -> None:
        """Set up the service without loading the model.

        The model is loaded lazily, on the first transcription. Loading it at
        startup would add tens of seconds to every restart even for someone who
        only ever types.

        Args:
            settings: Application settings, supplying the model size, device,
                and the upload limits.
        """
        self._settings = settings
        self._model: Any = None
        self._load_lock = asyncio.Lock()

    async def _ensure_model(self) -> Any:
        """Load the speech model, once, on first use.

        Returns:
            The loaded model.

        Raises:
            TranscriptionUnavailableError: If voice input is switched off, or
                the optional dependencies are not installed.
        """
        if self._model is not None:
            return self._model

        async with self._load_lock:
            if self._model is not None:  # another request loaded it while we waited
                return self._model

            if not self._settings.stt_enabled:
                raise TranscriptionUnavailableError(
                    "It is switched off in configuration. Set STT_ENABLED=true to enable it."
                )

            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise TranscriptionUnavailableError(
                    "The speech-to-text libraries are not installed. Install them with "
                    "'uv sync --extra voice' and restart the server. Typing works "
                    "normally in the meantime."
                ) from exc

            _log.info(
                "stt_model_loading",
                stt_model=self._settings.stt_model_size,
                component="stt",
            )
            started = time.perf_counter()
            # Loading is CPU-bound and blocking, so it runs in a worker thread.
            # Doing it inline would freeze every other request in the server
            # for as long as it takes.
            self._model = await asyncio.to_thread(
                WhisperModel,
                self._settings.stt_model_size,
                device=self._settings.stt_device,
                compute_type=self._settings.stt_compute_type,
            )
            _log.info(
                "stt_model_loaded",
                stt_model=self._settings.stt_model_size,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            return self._model

    def validate_upload(self, data: bytes, content_type: str | None) -> None:
        """Check an uploaded recording before spending any effort on it.

        An uploaded file is untrusted input like any other. Two limits apply:
        a size cap, so a huge upload cannot exhaust memory, and a content type
        check, so obviously wrong files are rejected cheaply.

        Args:
            data: The uploaded bytes.
            content_type: The declared type, which the browser sets.

        Raises:
            ApiError: If the upload is empty, too large, or not audio. The
                declared type is treated as a hint only — a caller can claim
                anything — so the real protection is the size limit and the
                fact that the decoder rejects what it cannot parse.
        """
        if not data:
            raise ApiError(400, "empty_audio", "No audio was received.")
        if len(data) > self._settings.stt_max_upload_bytes:
            limit_mb = self._settings.stt_max_upload_bytes / 1_048_576
            raise ApiError(
                413,
                "audio_too_large",
                f"That recording is larger than the {limit_mb:.0f} MB limit. "
                "Try recording a shorter message.",
            )
        if content_type and not content_type.startswith(("audio/", "video/webm", "application/octet-stream")):
            raise ApiError(
                415,
                "unsupported_audio_type",
                f"'{content_type}' is not a supported audio format.",
            )

    async def transcribe(self, data: bytes, content_type: str | None = None) -> Transcription:
        """Turn a recording into text, entirely on this machine.

        Args:
            data: The uploaded audio bytes.
            content_type: The declared content type, used for validation.

        Returns:
            The transcript and its metadata.

        Raises:
            ApiError: If the upload fails validation or cannot be decoded.
            TranscriptionUnavailableError: If speech-to-text is not available.
        """
        self.validate_upload(data, content_type)
        model = await self._ensure_model()

        started = time.perf_counter()
        try:
            segments, info = await asyncio.to_thread(
                model.transcribe,
                io.BytesIO(data),
                beam_size=1,  # fastest setting; adequate for short game commands
                vad_filter=True,  # skip silence, which speeds things up considerably
            )
            text = " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as exc:  # noqa: BLE001 - any decode failure looks the same to the user
            _log.warning("stt_failed", audio_bytes=len(data))
            raise ApiError(
                422,
                "audio_unreadable",
                "That recording could not be read. Try recording again.",
            ) from exc

        duration = float(getattr(info, "duration", 0.0))
        if duration > self._settings.stt_max_seconds:
            raise ApiError(
                413,
                "audio_too_long",
                f"That recording is longer than the {self._settings.stt_max_seconds} "
                "second limit.",
            )

        # Note the log fields: how many bytes, how many seconds, how many
        # characters came out. Never the transcript itself — those are the
        # player's words.
        _log.info(
            "stt_completed",
            audio_bytes=len(data),
            audio_seconds=round(duration, 2),
            transcript_chars=len(text),
            stt_model=self._settings.stt_model_size,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

        return Transcription(
            text=text,
            duration_seconds=duration,
            language=str(getattr(info, "language", "en")),
            model=self._settings.stt_model_size,
        )
