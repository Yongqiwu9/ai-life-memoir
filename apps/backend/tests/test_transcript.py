import uuid


def _register_and_login(client, email: str, password: str = "strong-password-1"):
    register = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert register.status_code == 201
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _setup_audio(client, headers):
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
        json={"original_filename": "recording.wav"},
        headers=headers,
    ).json()
    return audio


def _create_transcript(client, headers, audio_id, **overrides):
    payload: dict = {"provider": "whisper", "model": "whisper-1", "language": "zh"}
    payload.update(overrides)
    response = client.post(f"/api/v1/audios/{audio_id}/transcripts", json=payload, headers=headers)
    assert response.status_code == 201
    return response.json()


def test_create_transcript(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    audio = _setup_audio(client, headers)

    transcript = _create_transcript(client, headers, audio["id"])

    assert uuid.UUID(transcript["id"])
    assert transcript["audio_recording_id"] == audio["id"]
    assert transcript["provider"] == "whisper"
    assert transcript["status"] == "pending"
    assert transcript["text"] is None


def test_get_own_transcript(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    audio = _setup_audio(client, headers)
    transcript = _create_transcript(client, headers, audio["id"])

    response = client.get(f"/api/v1/transcripts/{transcript['id']}", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == transcript["id"]


def test_list_transcripts_of_own_audio(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    audio = _setup_audio(client, headers)
    _create_transcript(client, headers, audio["id"])
    _create_transcript(client, headers, audio["id"])

    listing = client.get(f"/api/v1/audios/{audio['id']}/transcripts", headers=headers).json()

    assert listing["total"] == 2


def test_transcript_of_other_user_returns_404(client) -> None:
    headers_a = _register_and_login(client, "a@example.com")
    headers_b = _register_and_login(client, "b@example.com")
    audio_a = _setup_audio(client, headers_a)
    transcript_a = _create_transcript(client, headers_a, audio_a["id"])

    response = client.get(f"/api/v1/transcripts/{transcript_a['id']}", headers=headers_b)

    assert response.status_code == 404


def test_invalid_audio_id_returns_404(client) -> None:
    headers = _register_and_login(client, "owner@example.com")

    response = client.post(
        f"/api/v1/audios/{uuid.uuid4()}/transcripts",
        json={},
        headers=headers,
    )

    assert response.status_code == 404


def test_failed_transcript_can_be_saved(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    audio = _setup_audio(client, headers)

    transcript = _create_transcript(client, headers, audio["id"], status="failed")

    assert transcript["status"] == "failed"
