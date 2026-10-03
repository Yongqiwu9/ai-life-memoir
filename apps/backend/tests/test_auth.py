import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import settings


def _register(client, email: str = "user@example.com", password: str = "strong-password-1"):
    return client.post("/api/v1/auth/register", json={"email": email, "password": password})


def _login(client, email: str = "user@example.com", password: str = "strong-password-1"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _auth_headers(client, email: str = "user@example.com", password: str = "strong-password-1"):
    _register(client, email=email, password=password)
    token = _login(client, email=email, password=password).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_register_returns_safe_user(client) -> None:
    response = _register(client)

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "user@example.com"
    assert uuid.UUID(data["id"])
    assert data["is_active"] is True
    assert "password" not in data
    assert "password_hash" not in data


def test_register_normalizes_email(client) -> None:
    response = _register(client, email="  User@Example.COM ")

    assert response.status_code == 201
    assert response.json()["email"] == "user@example.com"


def test_register_rejects_duplicate_email(client) -> None:
    assert _register(client).status_code == 201

    response = _register(client, email="User@Example.com")

    assert response.status_code == 409


def test_login_returns_signed_token(client) -> None:
    _register(client)

    response = _login(client)

    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    payload = jwt.decode(
        data["access_token"],
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
    assert "sub" in payload
    assert "exp" in payload


def test_login_wrong_password_returns_generic_error(client) -> None:
    _register(client)

    response = _login(client, password="wrong-password")

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid email or password"


def test_login_unknown_user_returns_same_generic_error(client) -> None:
    response = _login(client, email="nobody@example.com", password="whatever-password")

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid email or password"


def test_jwt_subject_matches_user(client) -> None:
    _register(client)
    token = _login(client).json()["access_token"]

    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
    me = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}).json()

    assert payload["sub"] == me["id"]


def test_me_returns_current_user(client) -> None:
    headers = _auth_headers(client)

    response = client.get("/api/v1/users/me", headers=headers)

    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"


def test_me_requires_token(client) -> None:
    response = client.get("/api/v1/users/me")

    assert response.status_code == 401


def test_me_rejects_invalid_token(client) -> None:
    response = client.get("/api/v1/users/me", headers={"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 401


def test_me_rejects_expired_token(client) -> None:
    now = datetime.now(UTC)
    payload = {"sub": str(uuid.uuid4()), "exp": now - timedelta(seconds=1)}
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    response = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_me_ignores_user_id_hint(client) -> None:
    headers = _auth_headers(client)
    _register(client, email="other@example.com", password="strong-password-2")

    response = client.get("/api/v1/users/me?user_id=not-used", headers=headers)

    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"
