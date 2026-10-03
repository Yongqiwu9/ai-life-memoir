import os
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "apps" / "backend"
os.chdir(BACKEND_DIR)

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.crud import user as user_crud
from app.database.session import SessionLocal
from app.main import app
from app.models.user import User


def _register_and_login(client, email: str, password: str) -> dict[str, str]:
    register = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert register.status_code == 201, register.text
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _cleanup(emails: list[str]) -> None:
    db = SessionLocal()
    try:
        for email in emails:
            user = user_crud.get_user_by_email(db, email)
            if user is not None:
                db.execute(delete(User).where(User.id == user.id))
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

            family_a = client.post("/api/v1/families", json={"name": "Family A"}, headers=headers_a).json()
            member_a = client.post(
                f"/api/v1/families/{family_a['id']}/members",
                json={"name": "Member A"},
                headers=headers_a,
            ).json()
            family_b = client.post("/api/v1/families", json={"name": "Family B"}, headers=headers_b).json()
            member_b = client.post(
                f"/api/v1/families/{family_b['id']}/members",
                json={"name": "Member B"},
                headers=headers_b,
            ).json()

            interview_a = client.post(
                f"/api/v1/family-members/{member_a['id']}/interviews",
                json={"title": "Interview A", "type": "life_story"},
                headers=headers_a,
            ).json()
            interview_b = client.post(
                f"/api/v1/family-members/{member_b['id']}/interviews",
                json={"title": "Interview B", "type": "life_story"},
                headers=headers_b,
            ).json()
            session_a = client.post(
                f"/api/v1/interviews/{interview_a['id']}/sessions",
                json={},
                headers=headers_a,
            ).json()
            message_a = client.post(
                f"/api/v1/sessions/{session_a['id']}/messages",
                json={"content": "我小时候住在上海。"},
                headers=headers_a,
            ).json()

            check(
                "A create interview",
                interview_a.get("title") == "Interview A",
            )
            check("A create session", session_a.get("interview_id") == interview_a["id"])
            check(
                "A create user message",
                message_a.get("role") == "user" and message_a.get("sequence") == 1,
            )
            check(
                "A read A interview",
                client.get(f"/api/v1/interviews/{interview_a['id']}", headers=headers_a).status_code
                == 200,
            )
            check(
                "B read A interview denied",
                client.get(f"/api/v1/interviews/{interview_a['id']}", headers=headers_b).status_code
                == 404,
            )
            check(
                "B create session in A interview denied",
                client.post(
                    f"/api/v1/interviews/{interview_a['id']}/sessions",
                    json={},
                    headers=headers_b,
                ).status_code
                == 404,
            )
            check(
                "B create message in A session denied",
                client.post(
                    f"/api/v1/sessions/{session_a['id']}/messages",
                    json={"content": "Intruder"},
                    headers=headers_b,
                ).status_code
                == 404,
            )
            check(
                "A update A interview",
                client.patch(
                    f"/api/v1/interviews/{interview_a['id']}",
                    json={"status": "completed"},
                    headers=headers_a,
                ).status_code
                == 200,
            )
            check(
                "A delete A interview",
                client.delete(f"/api/v1/interviews/{interview_a['id']}", headers=headers_a).status_code
                == 204,
            )
            check(
                "A delete B interview denied",
                client.delete(f"/api/v1/interviews/{interview_b['id']}", headers=headers_a).status_code
                == 404,
            )
    finally:
        _cleanup([email_a, email_b])

    return 0 if all(ok for _, ok in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
