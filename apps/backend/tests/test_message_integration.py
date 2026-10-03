import uuid

from app.services import interview_message as message_service


def _register_and_login(client, email: str, password: str = "strong-password-1"):
    register = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert register.status_code == 201
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _setup_segment(client, headers):
    family = client.post("/api/v1/families", json={"name": "My Family"}, headers=headers).json()
    member = client.post(
        f"/api/v1/families/{family['id']}/members",
        json={"name": "Member"},
        headers=headers,
    ).json()
    interview = client.post(
        f"/api/v1/family-members/{member['id']}/interviews",
        json={"title": "Interview", "type": "life_story"},
        headers=headers,
    ).json()
    session = client.post(
        f"/api/v1/interviews/{interview['id']}/sessions",
        json={},
        headers=headers,
    ).json()
    audio = client.post(
        f"/api/v1/sessions/{session['id']}/audios",
        json={},
        headers=headers,
    ).json()
    transcript = client.post(
        f"/api/v1/audios/{audio['id']}/transcripts",
        json={},
        headers=headers,
    ).json()
    segment = client.post(
        f"/api/v1/transcripts/{transcript['id']}/segments",
        json={"text": "我小时候住在上海。"},
        headers=headers,
    ).json()
    return session, segment


def test_audio_segment_links_to_user_message(client, db_session) -> None:
    headers = _register_and_login(client, "owner@example.com")
    me = client.get("/api/v1/users/me", headers=headers).json()
    session, segment = _setup_segment(client, headers)

    message = message_service.create_transcript_message(
        db_session,
        user_id=uuid.UUID(me["id"]),
        session_id=uuid.UUID(session["id"]),
        segment_id=uuid.UUID(segment["id"]),
    )

    assert message.role == "user"
    assert message.source == "audio_transcript"
    assert message.transcript_segment_id == uuid.UUID(segment["id"])
    assert message.content == segment["text"]


def test_client_cannot_create_assistant_or_ai_message(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    session, _ = _setup_segment(client, headers)

    assistant_role = client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"role": "assistant", "content": "AI reply"},
        headers=headers,
    )
    ai_source = client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"role": "user", "source": "ai_generated", "content": "AI reply"},
        headers=headers,
    )

    assert assistant_role.status_code == 422
    assert ai_source.status_code == 422


def test_text_message_does_not_require_segment(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    session, _ = _setup_segment(client, headers)

    response = client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"content": "我直接打字。"},
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["role"] == "user"
    assert response.json()["source"] == "text"
    assert response.json()["transcript_segment_id"] is None
