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


def test_create_message_in_own_session(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    session = _setup_session(client, headers)

    response = client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"content": "我小时候住在上海。"},
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["role"] == "user"
    assert response.json()["content"] == "我小时候住在上海。"
    assert response.json()["sequence"] == 1


def test_list_messages_in_sequence_order(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    session = _setup_session(client, headers)
    client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"content": "第一条"},
        headers=headers,
    )
    client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"content": "第二条"},
        headers=headers,
    )

    listing = client.get(f"/api/v1/sessions/{session['id']}/messages", headers=headers).json()

    assert listing["total"] == 2
    assert [item["sequence"] for item in listing["items"]] == [1, 2]
    assert [item["content"] for item in listing["items"]] == ["第一条", "第二条"]


def test_create_message_in_other_users_session_returns_404(client) -> None:
    headers_a = _register_and_login(client, "a@example.com")
    headers_b = _register_and_login(client, "b@example.com")
    session_b = _setup_session(client, headers_b)

    response = client.post(
        f"/api/v1/sessions/{session_b['id']}/messages",
        json={"content": "Intruder"},
        headers=headers_a,
    )

    assert response.status_code == 404


def test_list_messages_of_other_users_session_returns_404(client) -> None:
    headers_a = _register_and_login(client, "a@example.com")
    headers_b = _register_and_login(client, "b@example.com")
    session_b = _setup_session(client, headers_b)

    response = client.get(f"/api/v1/sessions/{session_b['id']}/messages", headers=headers_a)

    assert response.status_code == 404


def test_reject_system_role(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    session = _setup_session(client, headers)

    response = client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"role": "system", "content": "system prompt"},
        headers=headers,
    )

    assert response.status_code == 422


def test_reject_assistant_role(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    session = _setup_session(client, headers)

    response = client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"role": "assistant", "content": "assistant reply"},
        headers=headers,
    )

    assert response.status_code == 422


def test_reject_empty_content(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    session = _setup_session(client, headers)

    response = client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"content": ""},
        headers=headers,
    )

    assert response.status_code == 422
