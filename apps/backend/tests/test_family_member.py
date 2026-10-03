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


def test_create_member_in_own_family(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    family = _create_family(client, headers)

    member = _create_member(client, headers, family["id"], "母亲")

    assert uuid.UUID(member["id"])
    assert member["family_id"] == family["id"]
    assert member["name"] == "母亲"


def test_members_require_auth(client) -> None:
    response = client.get(f"/api/v1/families/{uuid.uuid4()}/members")

    assert response.status_code == 401


def test_list_members_of_own_family(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    family = _create_family(client, headers)
    _create_member(client, headers, family["id"], "父亲")
    _create_member(client, headers, family["id"], "母亲")

    listing = client.get(f"/api/v1/families/{family['id']}/members", headers=headers).json()

    assert listing["total"] == 2
    assert {item["name"] for item in listing["items"]} == {"父亲", "母亲"}


def test_list_members_does_not_leak_other_users_members(client) -> None:
    headers_a = _register_and_login(client, "a@example.com")
    headers_b = _register_and_login(client, "b@example.com")
    family_a = _create_family(client, headers_a, "Family A")
    family_b = _create_family(client, headers_b, "Family B")
    _create_member(client, headers_a, family_a["id"], "Member A")
    _create_member(client, headers_b, family_b["id"], "Member B")

    listing_a = client.get(f"/api/v1/families/{family_a['id']}/members", headers=headers_a).json()
    listing_b = client.get(f"/api/v1/families/{family_b['id']}/members", headers=headers_b).json()

    assert [item["name"] for item in listing_a["items"]] == ["Member A"]
    assert [item["name"] for item in listing_b["items"]] == ["Member B"]
    assert listing_a["total"] == 1
    assert listing_b["total"] == 1


def test_list_members_isolated_between_families(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    family_one = _create_family(client, headers, "Family One")
    family_two = _create_family(client, headers, "Family Two")
    _create_member(client, headers, family_one["id"], "Member One")
    _create_member(client, headers, family_two["id"], "Member Two")

    listing_one = client.get(
        f"/api/v1/families/{family_one['id']}/members",
        headers=headers,
    ).json()
    listing_two = client.get(
        f"/api/v1/families/{family_two['id']}/members",
        headers=headers,
    ).json()

    assert [item["name"] for item in listing_one["items"]] == ["Member One"]
    assert [item["name"] for item in listing_two["items"]] == ["Member Two"]


def test_list_members_of_other_users_family_returns_404(client) -> None:
    headers_a = _register_and_login(client, "a@example.com")
    headers_b = _register_and_login(client, "b@example.com")
    family_b = _create_family(client, headers_b)
    _create_member(client, headers_b, family_b["id"], "Member B")

    response = client.get(f"/api/v1/families/{family_b['id']}/members", headers=headers_a)

    assert response.status_code == 404


def test_get_own_member(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    family = _create_family(client, headers)
    member = _create_member(client, headers, family["id"])

    response = client.get(
        f"/api/v1/families/{family['id']}/members/{member['id']}",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["id"] == member["id"]


def test_update_own_member(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    family = _create_family(client, headers)
    member = _create_member(client, headers, family["id"])

    response = client.patch(
        f"/api/v1/families/{family['id']}/members/{member['id']}",
        json={"name": "Renamed Member"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed Member"


def test_delete_own_member(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    family = _create_family(client, headers)
    member = _create_member(client, headers, family["id"])

    response = client.delete(
        f"/api/v1/families/{family['id']}/members/{member['id']}",
        headers=headers,
    )

    assert response.status_code == 204
    assert (
        client.get(
            f"/api/v1/families/{family['id']}/members/{member['id']}",
            headers=headers,
        ).status_code
        == 404
    )


def test_create_member_in_other_users_family_returns_404(client) -> None:
    headers_a = _register_and_login(client, "a@example.com")
    headers_b = _register_and_login(client, "b@example.com")
    family_b = _create_family(client, headers_b)

    response = client.post(
        f"/api/v1/families/{family_b['id']}/members",
        json={"name": "Intruder"},
        headers=headers_a,
    )

    assert response.status_code == 404


def test_get_other_users_member_returns_404(client) -> None:
    headers_a = _register_and_login(client, "a@example.com")
    headers_b = _register_and_login(client, "b@example.com")
    family_b = _create_family(client, headers_b)
    member_b = _create_member(client, headers_b, family_b["id"])

    response = client.get(
        f"/api/v1/families/{family_b['id']}/members/{member_b['id']}",
        headers=headers_a,
    )

    assert response.status_code == 404


def test_update_other_users_member_returns_404(client) -> None:
    headers_a = _register_and_login(client, "a@example.com")
    headers_b = _register_and_login(client, "b@example.com")
    family_b = _create_family(client, headers_b)
    member_b = _create_member(client, headers_b, family_b["id"])

    response = client.patch(
        f"/api/v1/families/{family_b['id']}/members/{member_b['id']}",
        json={"name": "Hacked"},
        headers=headers_a,
    )

    assert response.status_code == 404


def test_delete_other_users_member_returns_404(client) -> None:
    headers_a = _register_and_login(client, "a@example.com")
    headers_b = _register_and_login(client, "b@example.com")
    family_b = _create_family(client, headers_b)
    member_b = _create_member(client, headers_b, family_b["id"])

    response = client.delete(
        f"/api/v1/families/{family_b['id']}/members/{member_b['id']}",
        headers=headers_a,
    )

    assert response.status_code == 404
    assert (
        client.get(
            f"/api/v1/families/{family_b['id']}/members/{member_b['id']}",
            headers=headers_b,
        ).status_code
        == 200
    )


def test_member_id_under_wrong_family_returns_404(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    family_one = _create_family(client, headers, "Family One")
    family_two = _create_family(client, headers, "Family Two")
    member = _create_member(client, headers, family_one["id"])

    wrong = client.get(
        f"/api/v1/families/{family_two['id']}/members/{member['id']}",
        headers=headers,
    )
    right = client.get(
        f"/api/v1/families/{family_one['id']}/members/{member['id']}",
        headers=headers,
    )

    assert wrong.status_code == 404
    assert right.status_code == 200


def test_cross_user_member_under_own_family_returns_404(client) -> None:
    headers_a = _register_and_login(client, "a@example.com")
    headers_b = _register_and_login(client, "b@example.com")
    family_a = _create_family(client, headers_a)
    family_b = _create_family(client, headers_b)
    member_b = _create_member(client, headers_b, family_b["id"])

    response = client.get(
        f"/api/v1/families/{family_a['id']}/members/{member_b['id']}",
        headers=headers_a,
    )

    assert response.status_code == 404
