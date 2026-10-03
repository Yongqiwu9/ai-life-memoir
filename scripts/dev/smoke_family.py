import os
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "apps" / "backend"
os.chdir(BACKEND_DIR)

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.crud import user as user_crud
from app.database.session import SessionLocal
from app.main import app
from app.models.family import Family


def _register_and_login(client, email: str, password: str) -> dict[str, str]:
    register = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert register.status_code == 201, register.text
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _create_family(client, headers, name: str) -> dict:
    response = client.post("/api/v1/families", json={"name": name}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _create_member(client, headers, family_id: str, name: str) -> dict:
    response = client.post(
        f"/api/v1/families/{family_id}/members",
        json={"name": name},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _cleanup(email_a: str, email_b: str) -> None:
    db = SessionLocal()
    try:
        for email in (email_a, email_b):
            user = user_crud.get_user_by_email(db, email)
            if user is None:
                continue
            families = list(db.scalars(select(Family).where(Family.owner_id == user.id)).all())
            for family in families:
                db.delete(family)
            db.flush()
            db.delete(user)
        db.commit()
    finally:
        db.close()


def main() -> int:
    email_a = f"smoke-a-{uuid.uuid4().hex}@example.com"
    email_b = f"smoke-b-{uuid.uuid4().hex}@example.com"
    password = "smoke-password-1"
    checks: list[tuple[str, bool]] = []

    def check(label: str, condition: bool) -> None:
        checks.append((label, condition))
        print(f"{label}: {'PASS' if condition else 'FAIL'}")

    try:
        with TestClient(app) as client:
            headers_a = _register_and_login(client, email_a, password)
            headers_b = _register_and_login(client, email_b, password)

            family_a = _create_family(client, headers_a, "Family A")
            family_b = _create_family(client, headers_b, "Family B")
            member_a = _create_member(client, headers_a, family_a["id"], "Member A")
            member_b = _create_member(client, headers_b, family_b["id"], "Member B")

            check(
                "A read A family",
                client.get(f"/api/v1/families/{family_a['id']}", headers=headers_a).status_code == 200,
            )
            check(
                "B read B family",
                client.get(f"/api/v1/families/{family_b['id']}", headers=headers_b).status_code == 200,
            )
            check(
                "A read B family denied",
                client.get(f"/api/v1/families/{family_b['id']}", headers=headers_a).status_code == 404,
            )
            check(
                "B read A family denied",
                client.get(f"/api/v1/families/{family_a['id']}", headers=headers_b).status_code == 404,
            )
            check(
                "A read B member denied",
                client.get(
                    f"/api/v1/families/{family_b['id']}/members/{member_b['id']}",
                    headers=headers_a,
                ).status_code
                == 404,
            )
            check(
                "B read A member denied",
                client.get(
                    f"/api/v1/families/{family_a['id']}/members/{member_a['id']}",
                    headers=headers_b,
                ).status_code
                == 404,
            )
            check(
                "A update A family",
                client.patch(
                    f"/api/v1/families/{family_a['id']}",
                    json={"name": "Family A Renamed"},
                    headers=headers_a,
                ).status_code
                == 200,
            )
            check(
                "A update B family denied",
                client.patch(
                    f"/api/v1/families/{family_b['id']}",
                    json={"name": "Hacked"},
                    headers=headers_a,
                ).status_code
                == 404,
            )
            check(
                "A delete A family",
                client.delete(f"/api/v1/families/{family_a['id']}", headers=headers_a).status_code
                == 204,
            )
            check(
                "A delete B family denied",
                client.delete(f"/api/v1/families/{family_b['id']}", headers=headers_a).status_code
                == 404,
            )
    finally:
        _cleanup(email_a, email_b)

    return 0 if all(ok for _, ok in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
