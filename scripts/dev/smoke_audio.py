import os
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "apps" / "backend"
os.chdir(BACKEND_DIR)

from fastapi.testclient import TestClient
from sqlalchemy import delete

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

            family = client.post("/api/v1/families", json={"name": "Family A"}, headers=headers_a).json()
            member = client.post(
                f"/api/v1/families/{family['id']}/members",
                json={"name": "Member A"},
                headers=headers_a,
            ).json()
            interview = client.post(
                f"/api/v1/family-members/{member['id']}/interviews",
                json={"title": "Interview A", "type": "life_story"},
                headers=headers_a,
            ).json()
            session = client.post(
                f"/api/v1/interviews/{interview['id']}/sessions",
                json={},
                headers=headers_a,
            ).json()
            audio = client.post(
                f"/api/v1/sessions/{session['id']}/audios",
                json={"original_filename": "recording.wav", "mime_type": "audio/wav"},
                headers=headers_a,
            ).json()
            transcript = client.post(
                f"/api/v1/audios/{audio['id']}/transcripts",
                json={"provider": "whisper", "model": "whisper-1", "language": "zh"},
                headers=headers_a,
            ).json()
            segment_one = client.post(
                f"/api/v1/transcripts/{transcript['id']}/segments",
                json={"text": "第一句", "sequence": 1, "start_ms": 0, "end_ms": 800},
                headers=headers_a,
            ).json()
            segment_two = client.post(
                f"/api/v1/transcripts/{transcript['id']}/segments",
                json={"text": "第二句", "sequence": 2, "start_ms": 900, "end_ms": 1600},
                headers=headers_a,
            ).json()

            check("A create audio", audio.get("status") == "pending")
            check("A create transcript", transcript.get("status") == "pending")
            check(
                "segments ordered",
                [segment_one["id"], segment_two["id"]]
                == [
                    item["id"]
                    for item in client.get(
                        f"/api/v1/transcripts/{transcript['id']}/segments",
                        headers=headers_a,
                    ).json()["items"]
                ],
            )
            check(
                "A read audio",
                client.get(f"/api/v1/audios/{audio['id']}", headers=headers_a).status_code == 200,
            )
            check(
                "B read A audio denied",
                client.get(f"/api/v1/audios/{audio['id']}", headers=headers_b).status_code == 404,
            )
            check(
                "B read A transcript denied",
                client.get(
                    f"/api/v1/transcripts/{transcript['id']}",
                    headers=headers_b,
                ).status_code
                == 404,
            )
            check(
                "B read A segment denied",
                client.get(f"/api/v1/segments/{segment_one['id']}", headers=headers_b).status_code
                == 404,
            )
            check(
                "B create audio in A session denied",
                client.post(
                    f"/api/v1/sessions/{session['id']}/audios",
                    json={},
                    headers=headers_b,
                ).status_code
                == 404,
            )
    finally:
        _cleanup([email_a, email_b])

    return 0 if all(ok for _, ok in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
