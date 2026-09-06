"""Tests for crypto-shredding and the analytics allowlist."""

from __future__ import annotations

import uuid

import pytest

from app.services.analytics import AnalyticsRejected, AnalyticsService, bucket_duration


def _register(client, xsrf, username: str) -> dict:
    """Create an account and return its profile.

    Args:
        client: The test client.
        xsrf: The cross-site request forgery header.
        username: The username to register.

    Returns:
        The created profile.
    """
    return client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "display_name": username.title(),
            "email": f"{username}@example.com",
            "password": "correct-horse-battery-staple",
        },
        headers=xsrf,
    ).json()


def test_deleting_an_account_makes_its_data_unreadable(client, xsrf):
    """Crypto-shredding, demonstrated end to end.

    The account writes an encrypted campaign, then deletes itself. Afterwards
    the ciphertext is still sitting in storage — and is permanently unreadable,
    because the only key that could open it no longer exists.
    """
    profile = _register(client, xsrf, "shredme")
    auth = {**xsrf, "Authorization": f"Bearer stub.{profile['user_id']}"}

    client.post("/api/v1/campaigns", json={"title": "A Secret Story"}, headers=auth)

    response = client.post(
        "/api/v1/account/delete",
        json={"confirm_username": "shredme", "understood": True},
        headers=auth,
    )
    assert response.status_code == 200
    assert response.json()["shredded_at"]

    # The ciphertext survives — deletion did not go through the data.
    store = client.app.state.container.store
    assert any(row["title_ct"] for row in store.campaigns.values())

    # But the key is gone, so nothing can read it.
    user_row = store.users[uuid.UUID(profile["user_id"])]
    assert user_row["dek"] is None
    assert user_row["status"] == "shredded"


def test_a_deleted_account_can_no_longer_be_used(client, xsrf):
    """The session stops working the moment the key is destroyed."""
    profile = _register(client, xsrf, "goneaway")
    auth = {**xsrf, "Authorization": f"Bearer stub.{profile['user_id']}"}

    client.post(
        "/api/v1/account/delete",
        json={"confirm_username": "goneaway", "understood": True},
        headers=auth,
    )

    assert client.get("/api/v1/auth/me", headers=auth).status_code == 401


def test_a_deleted_account_cannot_be_found_by_email(client, xsrf):
    """Login lookup no longer matches, so the address is free to reuse."""
    _register(client, xsrf, "vanished")
    profile = client.post(
        "/api/v1/auth/login",
        json={"identifier": "vanished@example.com", "password": "correct-horse-battery-staple"},
        headers=xsrf,
    ).json()
    auth = {**xsrf, "Authorization": f"Bearer stub.{profile['user']['user_id']}"}

    client.post(
        "/api/v1/account/delete",
        json={"confirm_username": "vanished", "understood": True},
        headers=auth,
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": "vanished@example.com", "password": "correct-horse-battery-staple"},
        headers=xsrf,
    )
    assert response.status_code == 401


def test_deletion_requires_exact_confirmation(client, xsrf):
    """Deliberate friction on an action nobody can undo."""
    profile = _register(client, xsrf, "carefully")
    auth = {**xsrf, "Authorization": f"Bearer stub.{profile['user_id']}"}

    response = client.post(
        "/api/v1/account/delete",
        json={"confirm_username": "wrong-name", "understood": True},
        headers=auth,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "confirmation_required"


def test_analytics_rejects_an_undeclared_event():
    """An event not on the allowlist fails loudly rather than being dropped."""
    service = AnalyticsService()

    with pytest.raises(AnalyticsRejected, match="not a declared analytics event"):
        service.record(uuid.uuid4(), "user_typed_their_name")


def test_analytics_rejects_an_undeclared_feature_or_category():
    """Every enumerated field is checked, not just the event name."""
    service = AnalyticsService()

    with pytest.raises(AnalyticsRejected):
        service.record(uuid.uuid4(), "turn_taken", feature="secret_notes")
    with pytest.raises(AnalyticsRejected):
        service.record(uuid.uuid4(), "error_occurred", error_category="user_said_something_odd")


def test_analytics_uses_a_pseudonym_not_the_user_id():
    """The identifier recorded is unrelated to the account identifier."""
    service = AnalyticsService()
    user_id = uuid.uuid4()

    service.record(user_id, "turn_taken")
    recorded = service._events[-1]  # noqa: SLF001 - inspecting internals deliberately

    assert recorded.analytics_id != user_id
    assert service.analytics_id_for(user_id) == recorded.analytics_id


def test_severing_the_link_orphans_the_events_but_keeps_the_counts():
    """Deleting a user leaves anonymous totals rather than deleting history.

    This is the payoff of the two-plane design: the business metric survives,
    the person does not.
    """
    service = AnalyticsService()
    user_id = uuid.uuid4()

    service.record(user_id, "turn_taken")
    original_pseudonym = service.analytics_id_for(user_id)
    counts_before = service.snapshot()["turn_taken"]

    service.sever(user_id)

    assert service.snapshot()["turn_taken"] == counts_before
    # A new pseudonym is minted; the old events can never be reattached.
    assert service.analytics_id_for(user_id) != original_pseudonym


def test_durations_are_bucketed_not_exact():
    """An exact duration is close to unique and could act as a fingerprint."""
    assert bucket_duration(30) == "lt_1m"
    assert bucket_duration(1847) == "30_60m"
    assert bucket_duration(7200) == "gt_60m"


def test_country_is_taken_from_the_edge_header_only():
    """Geography arrives already computed, so no address is ever inspected."""
    assert AnalyticsService.country_from_headers({"cf-ipcountry": "gb"}) == "GB"
    assert AnalyticsService.country_from_headers({"cf-ipcountry": "XX"}) is None
    assert AnalyticsService.country_from_headers({}) is None
