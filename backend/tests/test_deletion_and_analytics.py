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


def test_deleting_an_account_removes_everything_it_owned(client, xsrf):
    """Deletion cascades: the account and all its content go together.

    The account writes a campaign, then deletes itself. Afterwards there is no
    user row and no campaign row — nothing is left behind for a later cleanup
    job to forget about.
    """
    profile = _register(client, xsrf, "deleteme")
    auth = {**xsrf, "Authorization": f"Bearer stub.{profile['user_id']}"}
    user_id = uuid.UUID(profile["user_id"])

    client.post("/api/v1/campaigns", json={"title": "A Secret Story"}, headers=auth)
    store = client.app.state.container.store
    assert any(row["user_id"] == user_id for row in store.campaigns.values())

    response = client.post(
        "/api/v1/account/delete",
        json={"confirm_username": "deleteme", "understood": True},
        headers=auth,
    )
    assert response.status_code == 200
    assert response.json()["deleted_at"]

    assert user_id not in store.users
    assert not any(row["user_id"] == user_id for row in store.campaigns.values())


def test_a_deleted_account_can_no_longer_be_used(client, xsrf):
    """The session stops working the moment the account is gone."""
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


def test_analytics_records_which_account_acted():
    """Events are attributed to the account, so counts can be per-user."""
    service = AnalyticsService()
    user_id = uuid.uuid4()

    service.record(user_id, "turn_taken")
    recorded = service._events[-1]  # noqa: SLF001 - inspecting internals deliberately

    assert recorded.user_id == user_id
    assert recorded.event_name == "turn_taken"


def test_deleting_a_user_removes_their_events_but_keeps_the_totals():
    """Deletion clears the raw events; the aggregate counters stay correct.

    The totals are what the product is measured by, and they should not drop
    retroactively every time somebody closes their account.
    """
    service = AnalyticsService()
    user_id = uuid.uuid4()

    service.record(user_id, "turn_taken")
    counts_before = service.snapshot()["turn_taken"]

    service.forget(user_id)

    assert service.snapshot()["turn_taken"] == counts_before
    assert not any(e.user_id == user_id for e in service._events)  # noqa: SLF001


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
