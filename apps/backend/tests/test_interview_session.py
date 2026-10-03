import uuid


def _register_and_login(client, email: str, password: str = "strong-password-1"):
    register_response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert register_response.status_code == 201
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_response.status_code == 200
    return {"Authorization": f"Bearer {login_response.json()['access_token']}"}


def _setup_interview(client, headers):
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
    return interview


def _create_session(client, headers, interview_id):
    response = client.post(
        f"/api/v1/interviews/{interview_id}/sessions",
        json={},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def test_create_session_in_own_interview(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    interview = _setup_interview(client, headers)

    session = _create_session(client, headers, interview["id"])

    assert uuid.UUID(session["id"])
    assert session["interview_id"] == interview["id"]
    assert session["status"] == "active"


def test_list_sessions_of_own_interview(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    interview = _setup_interview(client, headers)
    _create_session(client, headers, interview["id"])

    listing = client.get(f"/api/v1/interviews/{interview['id']}/sessions", headers=headers).json()

    assert listing["total"] == 1
    assert listing["items"][0]["interview_id"] == interview["id"]


def test_get_own_session(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    interview = _setup_interview(client, headers)
    session = _create_session(client, headers, interview["id"])

    response = client.get(f"/api/v1/sessions/{session['id']}", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == session["id"]


def test_create_session_in_other_users_interview_returns_404(client) -> None:
    headers_a = _register_and_login(client, "a@example.com")
    headers_b = _register_and_login(client, "b@example.com")
    interview_b = _setup_interview(client, headers_b)

    response = client.post(
        f"/api/v1/interviews/{interview_b['id']}/sessions",
        json={},
        headers=headers_a,
    )

    assert response.status_code == 404


def test_get_other_users_session_returns_404(client) -> None:
    headers_a = _register_and_login(client, "a@example.com")
    headers_b = _register_and_login(client, "b@example.com")
    interview_b = _setup_interview(client, headers_b)
    session_b = _create_session(client, headers_b, interview_b["id"])

    response = client.get(f"/api/v1/sessions/{session_b['id']}", headers=headers_a)

    assert response.status_code == 404


def test_list_sessions_isolated_between_interviews(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    interview_one = _setup_interview(client, headers)
    interview_two = _setup_interview(client, headers)
    session_one = _create_session(client, headers, interview_one["id"])
    session_two = _create_session(client, headers, interview_two["id"])

    list_one = client.get(
        f"/api/v1/interviews/{interview_one['id']}/sessions",
        headers=headers,
    ).json()
    list_two = client.get(
        f"/api/v1/interviews/{interview_two['id']}/sessions",
        headers=headers,
    ).json()

    assert [item["id"] for item in list_one["items"]] == [session_one["id"]]
    assert [item["id"] for item in list_two["items"]] == [session_two["id"]]
