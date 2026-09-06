"""Tests for the Dungeon Master conversation loop, with the AI faked."""

from __future__ import annotations


def test_a_turn_returns_narration(client, xsrf, fake_gemini):
    """The core loop: a message goes in, narration comes back."""
    response = client.post(
        "/api/v1/chat/turn",
        json={"message": "I push open the chapel door.", "input_mode": "typed"},
        headers=xsrf,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == fake_gemini.reply
    assert body["session_id"]
    assert body["usage"]["model_id"] == "gemini-3.5-flash"


def test_the_conversation_is_stored_and_can_be_read_back(client, xsrf):
    """Both sides of the exchange are persisted, encrypted, and retrievable."""
    session_id = client.post(
        "/api/v1/chat/turn", json={"message": "I look around."}, headers=xsrf
    ).json()["session_id"]

    messages = client.get(f"/api/v1/chat/sessions/{session_id}/messages").json()

    assert len(messages) == 2
    assert messages[0]["role"] == "player"
    assert messages[0]["content"] == "I look around."
    assert messages[1]["role"] == "dungeon_master"


def test_the_transcript_is_ciphertext_in_storage(client, xsrf):
    """What is actually stored bears no resemblance to what was typed.

    Reaches into the store deliberately. This is the test that proves the
    encryption is real rather than a comment claiming it is.
    """
    secret_line = "I whisper the password swordfish to the guard."
    client.post("/api/v1/chat/turn", json={"message": secret_line}, headers=xsrf)

    store = client.app.state.container.store
    stored_blobs = b"".join(row["content_ct"] for row in store.messages.values())

    assert b"swordfish" not in stored_blobs
    assert b"whisper" not in stored_blobs


def test_personal_data_is_scrubbed_before_it_reaches_the_model(client, xsrf, fake_gemini):
    """The address is stored for the player but never sent to Google."""
    client.post(
        "/api/v1/chat/turn",
        json={"message": "The note says to write to wren@example.com about the debt."},
        headers=xsrf,
    )

    sent = str(fake_gemini.calls[-1]["contents"])
    assert "wren@example.com" not in sent
    assert "[an email address]" in sent


def test_the_players_own_words_are_kept_unscrubbed_for_them(client, xsrf):
    """Scrubbing affects what leaves, not what the player can read back.

    This is their own campaign. They are entitled to their own notes; the
    scrubbing exists to protect them from a third party, not from themselves.
    """
    original = "The note says to write to wren@example.com about the debt."
    session_id = client.post(
        "/api/v1/chat/turn", json={"message": original}, headers=xsrf
    ).json()["session_id"]

    messages = client.get(f"/api/v1/chat/sessions/{session_id}/messages").json()
    assert messages[0]["content"] == original


def test_an_over_long_message_is_rejected(client, xsrf):
    """Input validation caps message length."""
    response = client.post("/api/v1/chat/turn", json={"message": "x" * 5000}, headers=xsrf)
    assert response.status_code == 422


def test_an_empty_message_is_rejected(client, xsrf):
    """There is nothing to narrate in response to nothing."""
    assert client.post("/api/v1/chat/turn", json={"message": ""}, headers=xsrf).status_code == 422


def test_unknown_request_fields_are_rejected(client, xsrf):
    """A typo produces an error rather than being silently ignored."""
    response = client.post(
        "/api/v1/chat/turn", json={"mesage": "typo in the field name"}, headers=xsrf
    )
    assert response.status_code == 422


def test_the_session_history_is_sent_to_the_model(client, xsrf, fake_gemini):
    """Later turns carry the earlier conversation, so the story continues."""
    session_id = client.post(
        "/api/v1/chat/turn", json={"message": "I enter the tavern."}, headers=xsrf
    ).json()["session_id"]

    client.post(
        "/api/v1/chat/turn",
        json={"message": "I order a drink.", "session_id": session_id},
        headers=xsrf,
    )

    sent = str(fake_gemini.calls[-1]["contents"])
    assert "I enter the tavern." in sent
    assert "I order a drink." in sent


def test_a_session_belonging_to_someone_else_is_not_readable(client, xsrf):
    """Transcripts are private to their owner."""
    session_id = client.post(
        "/api/v1/chat/turn", json={"message": "Something private."}, headers=xsrf
    ).json()["session_id"]

    other = client.post(
        "/api/v1/auth/register",
        json={
            "username": "snooper",
            "display_name": "Snooper",
            "email": "snooper@example.com",
            "password": "correct-horse-battery-staple",
        },
        headers=xsrf,
    ).json()

    response = client.get(
        f"/api/v1/chat/sessions/{session_id}/messages",
        headers={"Authorization": f"Bearer stub.{other['user_id']}"},
    )
    assert response.status_code == 404
