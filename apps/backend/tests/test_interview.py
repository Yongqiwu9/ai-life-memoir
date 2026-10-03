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


def _create_family(client, headers, name: str = "My Family"):
    response = client.post("/api/v1/families", json={"name": name}, headers=headers)
    assert response.status_code == 201
    return response.json()


def _create_member(client, headers, family_id, name: str = "Member"):
    response = client.post(
        f"/api/v1/families/{family_id}/members",
        json={"name": name},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def _create_interview(client, headers, member_id, title: str = "My Interview"):
    response = client.post(
        f"/api/v1/family-members/{member_id}/interviews",
        json={"title": title, "type": "life_story"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def test_create_interview(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    family = _create_family(client, headers)
    member = _create_member(client, headers, family["id"])

    interview = _create_interview(client, headers, member["id"], "爸爸的童年故事")

    assert uuid.UUID(interview["id"])
    assert interview["family_member_id"] == member["id"]
    assert interview["title"] == "爸爸的童年故事"
    assert interview["type"] == "life_story"
    assert interview["status"] == "draft"


def test_create_interview_for_other_users_member_returns_404(client) -> None:
    headers_a = _register_and_login(client, "a@example.com")
    headers_b = _register_and_login(client, "b@example.com")
    family_b = _create_family(client, headers_b)
    member_b = _create_member(client, headers_b, family_b["id"])

    response = client.post(
        f"/api/v1/family-members/{member_b['id']}/interviews",
        json={"title": "Intruder", "type": "life_story"},
        headers=headers_a,
    )

    assert response.status_code == 404


def test_interview_requires_auth(client) -> None:
    response = client.get(f"/api/v1/interviews/{uuid.uuid4()}")

    assert response.status_code == 401


def test_get_own_interview(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    family = _create_family(client, headers)
    member = _create_member(client, headers, family["id"])
    interview = _create_interview(client, headers, member["id"])

    response = client.get(f"/api/v1/interviews/{interview['id']}", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == interview["id"]


def test_get_other_users_interview_returns_404(client) -> None:
    headers_a = _register_and_login(client, "a@example.com")
    headers_b = _register_and_login(client, "b@example.com")
    family_b = _create_family(client, headers_b)
    member_b = _create_member(client, headers_b, family_b["id"])
    interview_b = _create_interview(client, headers_b, member_b["id"])

    response = client.get(f"/api/v1/interviews/{interview_b['id']}", headers=headers_a)

    assert response.status_code == 404


def test_update_own_interview(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    family = _create_family(client, headers)
    member = _create_member(client, headers, family["id"])
    interview = _create_interview(client, headers, member["id"])

    response = client.patch(
        f"/api/v1/interviews/{interview['id']}",
        json={"title": "Renamed Interview", "status": "completed"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Renamed Interview"
    assert response.json()["status"] == "completed"


def test_update_other_users_interview_returns_404(client) -> None:
    headers_a = _register_and_login(client, "a@example.com")
    headers_b = _register_and_login(client, "b@example.com")
    family_b = _create_family(client, headers_b)
    member_b = _create_member(client, headers_b, family_b["id"])
    interview_b = _create_interview(client, headers_b, member_b["id"])

    response = client.patch(
        f"/api/v1/interviews/{interview_b['id']}",
        json={"title": "Hacked"},
        headers=headers_a,
    )

    assert response.status_code == 404


def test_delete_own_interview(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    family = _create_family(client, headers)
    member = _create_member(client, headers, family["id"])
    interview = _create_interview(client, headers, member["id"])

    response = client.delete(f"/api/v1/interviews/{interview['id']}", headers=headers)

    assert response.status_code == 204
    assert client.get(f"/api/v1/interviews/{interview['id']}", headers=headers).status_code == 404


def test_delete_other_users_interview_returns_404(client) -> None:
    headers_a = _register_and_login(client, "a@example.com")
    headers_b = _register_and_login(client, "b@example.com")
    family_b = _create_family(client, headers_b)
    member_b = _create_member(client, headers_b, family_b["id"])
    interview_b = _create_interview(client, headers_b, member_b["id"])

    response = client.delete(f"/api/v1/interviews/{interview_b['id']}", headers=headers_a)

    assert response.status_code == 404
    assert (
        client.get(f"/api/v1/interviews/{interview_b['id']}", headers=headers_b).status_code == 200
    )


def test_list_interviews_isolated_between_members(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    family_a = _create_family(client, headers, "Family A")
    family_b = _create_family(client, headers, "Family B")
    member_a = _create_member(client, headers, family_a["id"], "Member A")
    member_b = _create_member(client, headers, family_b["id"], "Member B")
    _create_interview(client, headers, member_a["id"], "Interview A")
    _create_interview(client, headers, member_b["id"], "Interview B")

    list_a = client.get(
        f"/api/v1/family-members/{member_a['id']}/interviews",
        headers=headers,
    ).json()
    list_b = client.get(
        f"/api/v1/family-members/{member_b['id']}/interviews",
        headers=headers,
    ).json()

    assert [item["title"] for item in list_a["items"]] == ["Interview A"]
    assert [item["title"] for item in list_b["items"]] == ["Interview B"]
    assert list_a["total"] == 1
    assert list_b["total"] == 1


def test_list_interviews_does_not_leak_other_users(client) -> None:
    headers_a = _register_and_login(client, "a@example.com")
    headers_b = _register_and_login(client, "b@example.com")
    family_a = _create_family(client, headers_a)
    family_b = _create_family(client, headers_b)
    member_a = _create_member(client, headers_a, family_a["id"])
    member_b = _create_member(client, headers_b, family_b["id"])
    _create_interview(client, headers_a, member_a["id"], "Interview A")
    _create_interview(client, headers_b, member_b["id"], "Interview B")

    list_a = client.get(
        f"/api/v1/family-members/{member_a['id']}/interviews",
        headers=headers_a,
    ).json()
    list_b = client.get(
        f"/api/v1/family-members/{member_b['id']}/interviews",
        headers=headers_b,
    ).json()

    assert [item["title"] for item in list_a["items"]] == ["Interview A"]
    assert [item["title"] for item in list_b["items"]] == ["Interview B"]
