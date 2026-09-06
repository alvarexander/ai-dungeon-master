"""Tests for the security behaviour of the HTTP layer itself."""

from __future__ import annotations


def test_state_changing_requests_need_the_xsrf_token(client):
    """A POST without the token is refused.

    This is the cross-site request forgery defence. A malicious page can make
    the browser send the cookie, but cannot read it, so it cannot supply the
    matching header.
    """
    response = client.post("/api/v1/campaigns", json={"title": "Test"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "xsrf_failed"


def test_a_wrong_token_is_refused(client):
    """Supplying any old value does not work; it must match the cookie."""
    response = client.post(
        "/api/v1/campaigns", json={"title": "Test"}, headers={"X-XSRF-TOKEN": "guessed"}
    )
    assert response.status_code == 403


def test_reading_does_not_need_a_token(client):
    """GET requests change nothing, so they are exempt — and issue the token."""
    assert client.get("/api/v1/campaigns").status_code == 200


def test_the_token_cookie_is_readable_by_javascript(client):
    """The XSRF cookie must not be httponly, or the frontend cannot echo it.

    This is the one cookie in the application that is deliberately readable by
    scripts. It is safe because the token is not a credential: knowing it
    grants nothing without also holding the session.
    """
    response = client.get("/health")
    cookie_header = response.headers.get("set-cookie", "") or ""
    if "XSRF-TOKEN" in cookie_header:
        assert "httponly" not in cookie_header.lower()


def test_security_headers_are_present(client):
    """Every response instructs the browser to defend the user."""
    headers = client.get("/health").headers

    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert "microphone=()" in headers["Permissions-Policy"]
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]


def test_hsts_is_not_sent_locally(client):
    """HSTS locally would make the browser refuse plain HTTP to localhost.

    That is very difficult to undo and would break every other project on the
    machine, so it is only sent in production.
    """
    assert "Strict-Transport-Security" not in client.get("/health").headers


def test_every_response_carries_a_correlation_id(client):
    """The identifier a user quotes when reporting a problem."""
    response = client.get("/health")
    assert response.headers.get("X-Correlation-ID")


def test_correlation_ids_differ_between_requests(client):
    """Each request gets its own identifier so traces do not run together."""
    first = client.get("/health").headers["X-Correlation-ID"]
    second = client.get("/health").headers["X-Correlation-ID"]
    assert first != second


def test_a_supplied_correlation_id_is_not_blindly_trusted(client):
    """A hostile value is replaced rather than stamped onto our logs."""
    response = client.get(
        "/health", headers={"X-Correlation-ID": "injected\nfake-log-line: pwned"}
    )
    assert "\n" not in response.headers["X-Correlation-ID"]


def test_login_failures_are_indistinguishable(client, xsrf):
    """An unknown account and a wrong password produce identical responses.

    Anything more specific would let an attacker discover which email addresses
    are registered — defeating the point of encrypting the address.
    """
    unknown = client.post(
        "/api/v1/auth/login",
        json={"identifier": "nobody@example.com", "password": "some-long-password"},
        headers=xsrf,
    )
    client.post(
        "/api/v1/auth/register",
        json={
            "username": "knownuser",
            "display_name": "Known",
            "email": "known@example.com",
            "password": "correct-horse-battery-staple",
        },
        headers=xsrf,
    )
    wrong_password = client.post(
        "/api/v1/auth/login",
        json={"identifier": "known@example.com", "password": "definitely-not-it"},
        headers=xsrf,
    )

    assert unknown.status_code == wrong_password.status_code == 401
    assert unknown.json()["error"]["message"] == wrong_password.json()["error"]["message"]
    assert unknown.json()["error"]["code"] == wrong_password.json()["error"]["code"]


def test_validation_errors_do_not_echo_the_submitted_value(client, xsrf):
    """A rejected value is never repeated back, because errors reach the logs.

    FastAPI's default behaviour includes the offending input. That is exactly
    wrong here: a malformed email address would be echoed into the response and
    written to the log file.
    """
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "ok",
            "display_name": "Someone",
            "email": "definitely-not-an-email@@@bad",
            "password": "zxq",
        },
        headers=xsrf,
    )

    assert response.status_code == 422
    body = response.text
    assert "definitely-not-an-email" not in body
    assert "zxq" not in body
    # But it does say which field was wrong, which is what a developer needs.
    fields = {item["field"] for item in response.json()["error"]["fields"]}
    assert any("email" in field for field in fields)


def test_errors_carry_the_correlation_id(client):
    """Every error gives the user something to quote."""
    response = client.post("/api/v1/campaigns", json={"title": "x"})
    assert response.json()["error"]["correlation_id"]


def test_one_user_cannot_read_another_users_campaign(client, xsrf):
    """Ownership is checked, so guessing an identifier is not enough."""
    created = client.post(
        "/api/v1/campaigns", json={"title": "Private Story"}, headers=xsrf
    ).json()

    other = client.post(
        "/api/v1/auth/register",
        json={
            "username": "intruder",
            "display_name": "Intruder",
            "email": "intruder@example.com",
            "password": "correct-horse-battery-staple",
        },
        headers=xsrf,
    ).json()

    response = client.get(
        f"/api/v1/campaigns/{created['campaign_id']}",
        headers={**xsrf, "Authorization": f"Bearer stub.{other['user_id']}"},
    )
    # 404, not 403: telling them it exists but is not theirs would confirm the
    # identifier is real.
    assert response.status_code == 404


def test_the_readiness_check_reports_insecure_settings(client):
    """Running with development shortcuts is stated out loud, not hidden."""
    body = client.get("/health/ready").json()
    assert body["auth_mode"] == "stub"
    assert body["repository_backend"] == "memory"
    # At minimum: stubbed authentication, and storage that vanishes on restart.
    assert len(body["warnings"]) >= 2
