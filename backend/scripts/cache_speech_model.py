"""Downloads the speech-to-text model during the container build.

WHY THIS RUNS AT BUILD TIME RATHER THAN ON FIRST USE
The Whisper `base` model is about 145 MB. Without this, the first player to
press the microphone button waits for that download before anything happens —
and on a machine that has just scaled up from zero, they wait for it again.

Baking it into the container image makes the image larger and every request
fast. That is the right trade for something a person is waiting on.

FAILING IS NOT FATAL
If the voice libraries are not installed, or the download fails because the
build machine has no network, this prints why and exits successfully. The image
still builds and the application still runs — voice input then downloads the
model on first use, or reports that it is unavailable. A build should not fail
because an optional feature could not be pre-warmed.
"""

from __future__ import annotations

import sys


def main() -> int:
    """Download and cache the speech model.

    Returns:
        Always 0. See the note above about failing softly.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("Speech libraries not installed; skipping model cache.")  # noqa: T201
        return 0

    size = "base"
    try:
        WhisperModel(size, device="cpu", compute_type="int8")
    except Exception as exc:  # noqa: BLE001 - any failure here is non-fatal
        print(f"Could not cache the '{size}' speech model: {exc}")  # noqa: T201
        print("The image will still work; the model downloads on first use.")  # noqa: T201
        return 0

    print(f"Cached the '{size}' speech model.")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
