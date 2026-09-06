"""Lists the Gemini models your API key can actually use.

WHY THIS SCRIPT EXISTS
Google no longer publishes free-tier rate limits or model availability in its
documentation — those numbers are now per-account and shown only in the AI
Studio dashboard. So rather than this project asserting "model X is on the free
tier" and slowly becoming wrong, this script asks your key directly.

RUN IT WITH
    uv run python scripts/check_gemini_models.py

WHAT YOU SHOULD SEE
A list of model names, with the one currently configured in your .env marked.
If your configured model is not in the list, the script says so and suggests
one that is.

COMMON FAILURES
    "GEMINI_API_KEY is not set"   — you have not filled in .env yet.
    "403" or "401"                — the key is wrong, or was revoked.
    "Could not reach Google"      — no internet connection.
"""

from __future__ import annotations

import asyncio
import sys

import httpx


async def main() -> int:
    """List the models available to the configured API key.

    Returns:
        0 if the check succeeded, 1 otherwise, so this can be used in a script.
    """
    # Import after the docstring so that --help style usage is instant.
    sys.path.insert(0, ".")
    from app.config import get_settings

    try:
        settings = get_settings()
    except Exception as exc:  # noqa: BLE001 - configuration errors are the point here
        print(f"Configuration problem: {exc}")  # noqa: T201
        return 1

    key = settings.gemini_api_key.get_secret_value()
    if not key or key.startswith("CHANGE_ME"):
        print(  # noqa: T201
            "GEMINI_API_KEY is not set.\n"
            "Open backend/.env and replace CHANGE_ME_paste_your_key_here with your key.\n"
            "Instructions for getting one: docs/GEMINI.md"
        )
        return 1

    url = f"{settings.gemini_base_url.rstrip('/')}/v1beta/models"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(url, headers={"x-goog-api-key": key})
    except httpx.HTTPError as exc:
        print(f"Could not reach Google: {exc}")  # noqa: T201
        return 1

    if response.status_code != 200:
        print(  # noqa: T201
            f"Google refused the request (HTTP {response.status_code}).\n"
            "A 400 or 403 almost always means the API key is wrong or has been revoked.\n"
            "Generate a fresh one at https://aistudio.google.com/apikey"
        )
        return 1

    models = response.json().get("models", [])
    usable = sorted(
        model["name"].removeprefix("models/")
        for model in models
        if "generateContent" in model.get("supportedGenerationMethods", [])
    )

    configured = settings.gemini_model_id
    print(f"\nYour key can use {len(usable)} text-generation models.\n")  # noqa: T201
    for name in usable:
        marker = "  <-- currently configured in .env" if name == configured else ""
        print(f"  {name}{marker}")  # noqa: T201

    if configured not in usable:
        suggestion = next(
            (name for name in usable if "flash" in name and "preview" not in name),
            usable[0] if usable else "gemini-3.5-flash",
        )
        print(  # noqa: T201
            f"\nWARNING: '{configured}' is NOT in the list above, so calls to it will fail "
            f"with a 404.\nEdit backend/.env and set:  GEMINI_MODEL_ID={suggestion}"
        )
        return 1

    print(  # noqa: T201
        "\nYour configured model is available.\n"
        "Note: this lists which models you may call, not how many calls you get. "
        "Your actual free-tier quota is shown at:\n"
        "  https://aistudio.google.com/rate-limit\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
