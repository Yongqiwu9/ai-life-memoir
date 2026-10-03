import uuid


def _register_and_login(client, email: str, password: str = "strong-password-1"):
    register = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert register.status_code == 201
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _setup_session(client, headers):
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
    return session


def _create_audio(client, headers, session_id, **overrides):
    payload = {
        "original_filename": "recording.wav",
        "mime_type": "audio/wav",
        "size_bytes": 1024,
        "duration_ms": 3000,
    }
    payload.update(overrides)
    response = client.post(f"/api/v1/sessions/{session_id}/audios", json=payload, headers=headers)
    assert response.status_code == 201
    return response.json()


def test_create_audio(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    session = _setup_session(client, headers)

    audio = _create_audio(client, headers, session["id"])

    assert uuid.UUID(audio["id"])
    assert audio["session_id"] == session["id"]
    assert audio["status"] == "pending"
    assert audio["storage_key"] is None
    assert audio["original_filename"] == "recording.wav"


def test_get_own_audio(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    session = _setup_session(client, headers)
    audio = _create_audio(client, headers, session["id"])

    response = client.get(f"/api/v1/audios/{audio['id']}", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == audio["id"]


def test_list_audios_of_own_session(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    session = _setup_session(client, headers)
    _create_audio(client, headers, session["id"])
    _create_audio(client, headers, session["id"])

    listing = client.get(f"/api/v1/sessions/{session['id']}/audios", headers=headers).json()

    assert listing["total"] == 2
    assert all(item["session_id"] == session["id"] for item in listing["items"])


def test_audio_of_other_user_returns_404(client) -> None:
    headers_a = _register_and_login(client, "a@example.com")
    headers_b = _register_and_login(client, "b@example.com")
    session_a = _setup_session(client, headers_a)
    audio_a = _create_audio(client, headers_a, session_a["id"])

    get_response = client.get(f"/api/v1/audios/{audio_a['id']}", headers=headers_b)
    list_response = client.get(f"/api/v1/sessions/{session_a['id']}/audios", headers=headers_b)

    assert get_response.status_code == 404
    assert list_response.status_code == 404


def test_audio_cross_family_isolation(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    session_one = _setup_session(client, headers)
    session_two = _setup_session(client, headers)
    _create_audio(client, headers, session_one["id"])

    listing = client.get(f"/api/v1/sessions/{session_two['id']}/audios", headers=headers).json()

    assert listing["total"] == 0


def test_invalid_session_id_returns_404(client) -> None:
    headers = _register_and_login(client, "owner@example.com")

    response = client.post(
        f"/api/v1/sessions/{uuid.uuid4()}/audios",
        json={},
        headers=headers,
    )

    assert response.status_code == 404


def test_audio_schema_validation(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    session = _setup_session(client, headers)

    invalid_status = client.post(
        f"/api/v1/sessions/{session['id']}/audios",
        json={"status": "uploading"},
        headers=headers,
    )
    negative_size = client.post(
        f"/api/v1/sessions/{session['id']}/audios",
        json={"size_bytes": -1},
        headers=headers,
    )

    assert invalid_status.status_code == 422
    assert negative_size.status_code == 422
