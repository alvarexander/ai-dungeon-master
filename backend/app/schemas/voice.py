"""Response shapes for speech-to-text.

The request itself is not a Pydantic model, because it arrives as an uploaded
file rather than JSON. Its validation — size, duration, declared type — lives
in the endpoint and in `app/services/transcription.py`.

WHY THIS ENDPOINT EXISTS AT ALL
The browser has a built-in speech recognition feature that would make this
unnecessary. It is not used, because in Chrome it streams the raw microphone
audio to Google's servers — placing a recording of the user's voice, and
whatever is audible in their room, outside the boundary this whole design
protects. Transcription therefore happens on this server, using a local model.
See ADR-008 for the cost of that choice.
"""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import ApiModel


class TranscriptionResponse(ApiModel):
    """The text recovered from an uploaded recording."""

    transcript: str = Field(
        description=(
            "What the player said. Treated as personal data from the moment it exists: "
            "returned to the browser, and never written to a log."
        ),
        examples=["I push open the chapel door and hold up the lantern."],
    )
    duration_seconds: float = Field(description="Length of the audio.", examples=[3.8])
    language: str = Field(description="Detected language code.", examples=["en"])
    model: str = Field(description="Which local model transcribed it.", examples=["base"])
    processed_locally: bool = Field(
        default=True,
        description=(
            "Always true. Present so the frontend can state it plainly to the user, and "
            "so that any future change to this guarantee would be a visible API change "
            "rather than a quiet one."
        ),
    )
