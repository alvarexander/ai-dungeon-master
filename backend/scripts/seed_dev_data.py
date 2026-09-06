"""Fills a running local server with realistic, entirely invented data.

WHY SYNTHETIC DATA AND NEVER A COPY OF PRODUCTION
The tempting shortcut when debugging is to copy real data to a laptop. Doing
that would defeat every control in this project at once: a developer machine
has no KMS key policy, no audit log, no redacted logging, and is backed up to
somebody's personal cloud storage. One copy and the entire boundary is gone.

So local development uses invented people. This script generates them with
Faker, which produces names and addresses that look real and belong to nobody.

RUN IT WITH
    # Start the server first, in another terminal:
    uv run uvicorn app.main:app --reload --port 8000
    # Then:
    uv run python scripts/seed_dev_data.py

WHAT IT CREATES
Three accounts, each with a campaign and a character, and one campaign with a
short conversation already in it. Every account uses the password printed at
the end.

WHY IT TALKS TO THE RUNNING SERVER RATHER THAN THE STORE DIRECTLY
Phase 1 keeps everything in the server's memory, so there is no shared database
to write into. Going through the API also means the seeded data passes through
the same validation and encryption as real data — if the seed script works, the
real path works.
"""

from __future__ import annotations

import asyncio
import sys

import httpx

SEED_PASSWORD = "seeded-development-passphrase"  # noqa: S105 - local fixture, deliberately public

CAMPAIGNS = [
    {
        "title": "The Hollow Beneath Redmoor",
        "premise": "A mining village whose children have started sleepwalking towards the old shaft.",
        "tone": "mystery",
    },
    {
        "title": "Ashes of the Copper Coast",
        "premise": "Three rival harbours, one missing shipment, and a storm that will not break.",
        "tone": "gritty",
    },
    {
        "title": "The Very Reasonable Dragon",
        "premise": "A dragon has filed a formal complaint about the village's noise levels.",
        "tone": "comedic",
    },
]

CHARACTER_CLASSES = ["rogue", "cleric", "wizard"]


async def seed(base_url: str) -> int:
    """Create the demo accounts and their content.

    Args:
        base_url: Where the running server is listening.

    Returns:
        0 on success, 1 if the server could not be reached.
    """
    try:
        from faker import Faker
    except ImportError:
        print("Faker is not installed. Run: uv sync --group dev")  # noqa: T201
        return 1

    fake = Faker("en_GB")
    Faker.seed(20260906)  # same fake people every run, which makes debugging repeatable

    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        try:
            await client.get("/health")
        except httpx.HTTPError:
            print(  # noqa: T201
                f"Could not reach the server at {base_url}.\n"
                "Start it first, in another terminal:\n"
                "  uv run uvicorn app.main:app --reload --port 8000"
            )
            return 1

        # Every state-changing request needs the cross-site request forgery
        # token, exactly as the browser does. Seeding through the real API
        # means the seed data exercises the real protections.
        token = client.cookies.get("XSRF-TOKEN", "")
        headers = {"X-XSRF-TOKEN": token}

        created: list[str] = []

        for index, campaign_spec in enumerate(CAMPAIGNS):
            username = f"seed-player-{index + 1}"
            profile = await client.post(
                "/api/v1/auth/register",
                json={
                    "username": username,
                    "display_name": fake.first_name(),
                    # Invented address at a domain IANA reserves for
                    # documentation. It can never reach a real person.
                    "email": f"{username}@example.com",
                    "password": SEED_PASSWORD,
                },
                headers=headers,
            )
            if profile.status_code == 409:
                print(f"  {username} already exists, skipping.")  # noqa: T201
                continue
            if profile.status_code != 201:
                print(f"  Could not create {username}: {profile.text[:200]}")  # noqa: T201
                continue

            user_id = profile.json()["user_id"]
            auth = {**headers, "Authorization": f"Bearer stub.{user_id}"}

            campaign = await client.post("/api/v1/campaigns", json=campaign_spec, headers=auth)
            campaign_id = campaign.json()["campaign_id"]

            await client.post(
                f"/api/v1/campaigns/{campaign_id}/characters",
                json={
                    "name": f"{fake.first_name()} {fake.last_name()}",
                    "character_class": CHARACTER_CLASSES[index],
                    "level": index + 2,
                    "ancestry": ["Half-elf", "Dwarf", "Tiefling"][index],
                    "abilities": {
                        "strength": 8 + index * 2,
                        "dexterity": 16 - index,
                        "constitution": 12 + index,
                        "intelligence": 10 + index,
                        "wisdom": 14 - index,
                        "charisma": 11 + index,
                    },
                    "backstory": fake.sentence(nb_words=14),
                },
                headers=auth,
            )
            created.append(username)
            print(f"  Created {username} with '{campaign_spec['title']}'")  # noqa: T201

        print(  # noqa: T201
            f"\nSeeded {len(created)} accounts.\n"
            f"Sign in with any of them using the password: {SEED_PASSWORD}\n"
            "Every name and address above is invented. None of it belongs to a real person.\n"
            "\nNote: this data lives in the server's memory and is lost when it restarts. "
            "Run this script again after a restart.\n"
        )
    return 0


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    raise SystemExit(asyncio.run(seed(url)))
