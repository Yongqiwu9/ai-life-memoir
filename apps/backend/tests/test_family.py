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


def test_create_family(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    me = client.get("/api/v1/users/me", headers=headers).json()

    family = _create_family(client, headers, "我的家庭")

    assert uuid.UUID(family["id"])
    assert family["name"] == "我的家庭"
    assert family["owner_id"] == me["id"]


def test_family_requires_auth(client) -> None:
    response = client.get("/api/v1/families")

    assert response.status_code == 401


def test_list_families_shows_only_own(client) -> None:
    headers_a = _register_and_login(client, "a@example.com")
    headers_b = _register_and_login(client, "b@example.com")
    _create_family(client, headers_a, "Family A")
    _create_family(client, headers_b, "Family B")

    list_a = client.get("/api/v1/families", headers=headers_a).json()
    list_b = client.get("/api/v1/families", headers=headers_b).json()

    assert [item["name"] for item in list_a["items"]] == ["Family A"]
    assert [item["name"] for item in list_b["items"]] == ["Family B"]
    assert list_a["total"] == 1
    assert list_b["total"] == 1


def test_get_own_family(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    family = _create_family(client, headers)

    response = client.get(f"/api/v1/families/{family['id']}", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == family["id"]


def test_get_other_users_family_returns_404(client) -> None:
    headers_a = _register_and_login(client, "a@example.com")
    headers_b = _register_and_login(client, "b@example.com")
    family_b = _create_family(client, headers_b)

    response = client.get(f"/api/v1/families/{family_b['id']}", headers=headers_a)

    assert response.status_code == 404


def test_update_own_family(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    family = _create_family(client, headers)

    response = client.patch(
        f"/api/v1/families/{family['id']}",
        json={"name": "Renamed Family"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed Family"


def test_update_other_users_family_returns_404(client) -> None:
    headers_a = _register_and_login(client, "a@example.com")
    headers_b = _register_and_login(client, "b@example.com")
    family_b = _create_family(client, headers_b)

    response = client.patch(
        f"/api/v1/families/{family_b['id']}",
        json={"name": "Hacked"},
        headers=headers_a,
    )

    assert response.status_code == 404


def test_delete_own_family(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    family = _create_family(client, headers)

    response = client.delete(f"/api/v1/families/{family['id']}", headers=headers)

    assert response.status_code == 204
    assert client.get(f"/api/v1/families/{family['id']}", headers=headers).status_code == 404


def test_delete_other_users_family_returns_404(client) -> None:
    headers_a = _register_and_login(client, "a@example.com")
    headers_b = _register_and_login(client, "b@example.com")
    family_b = _create_family(client, headers_b)

    response = client.delete(f"/api/v1/families/{family_b['id']}", headers=headers_a)

    assert response.status_code == 404
    assert client.get(f"/api/v1/families/{family_b['id']}", headers=headers_b).status_code == 200


def test_list_families_pagination(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    _create_family(client, headers, "Family 1")
    _create_family(client, headers, "Family 2")

    page = client.get("/api/v1/families?page=1&page_size=1", headers=headers).json()

    assert page["total"] == 2
    assert len(page["items"]) == 1
    assert page["page"] == 1
    assert page["page_size"] == 1
