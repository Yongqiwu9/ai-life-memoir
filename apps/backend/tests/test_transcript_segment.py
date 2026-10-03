import uuid


def _register_and_login(client, email: str, password: str = "strong-password-1"):
    register = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert register.status_code == 201
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _setup_transcript(client, headers):
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
    return transcript


def _create_segment(client, headers, transcript_id, **overrides):
    payload = {"text": "我小时候住在上海。", "start_ms": 0, "end_ms": 1200}
    payload.update(overrides)
    response = client.post(
        f"/api/v1/transcripts/{transcript_id}/segments",
        json=payload,
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def test_create_segment(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    transcript = _setup_transcript(client, headers)

    segment = _create_segment(client, headers, transcript["id"])

    assert uuid.UUID(segment["id"])
    assert segment["transcript_id"] == transcript["id"]
    assert segment["sequence"] == 1
    assert segment["text"] == "我小时候住在上海。"


def test_get_own_segment(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    transcript = _setup_transcript(client, headers)
    segment = _create_segment(client, headers, transcript["id"])

    response = client.get(f"/api/v1/segments/{segment['id']}", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == segment["id"]


def test_list_segments_sorted_by_sequence(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    transcript = _setup_transcript(client, headers)
    _create_segment(client, headers, transcript["id"], text="第二句", sequence=2)
    _create_segment(client, headers, transcript["id"], text="第一句", sequence=1)

    listing = client.get(
        f"/api/v1/transcripts/{transcript['id']}/segments",
        headers=headers,
    ).json()

    assert [item["sequence"] for item in listing["items"]] == [1, 2]
    assert [item["text"] for item in listing["items"]] == ["第一句", "第二句"]


def test_segment_of_other_user_returns_404(client) -> None:
    headers_a = _register_and_login(client, "a@example.com")
    headers_b = _register_and_login(client, "b@example.com")
    transcript_a = _setup_transcript(client, headers_a)
    segment_a = _create_segment(client, headers_a, transcript_a["id"])

    response = client.get(f"/api/v1/segments/{segment_a['id']}", headers=headers_b)

    assert response.status_code == 404


def test_invalid_transcript_id_returns_404(client) -> None:
    headers = _register_and_login(client, "owner@example.com")

    response = client.post(
        f"/api/v1/transcripts/{uuid.uuid4()}/segments",
        json={"text": "x"},
        headers=headers,
    )

    assert response.status_code == 404


def test_start_ms_end_ms_validation(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    transcript = _setup_transcript(client, headers)

    reversed_range = client.post(
        f"/api/v1/transcripts/{transcript['id']}/segments",
        json={"text": "x", "start_ms": 2000, "end_ms": 1000},
        headers=headers,
    )
    negative_start = client.post(
        f"/api/v1/transcripts/{transcript['id']}/segments",
        json={"text": "x", "start_ms": -1},
        headers=headers,
    )
    bad_confidence = client.post(
        f"/api/v1/transcripts/{transcript['id']}/segments",
        json={"text": "x", "confidence": 1.5},
        headers=headers,
    )

    assert reversed_range.status_code == 422
    assert negative_start.status_code == 422
    assert bad_confidence.status_code == 422
