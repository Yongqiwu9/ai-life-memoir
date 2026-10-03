import os
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "apps" / "backend"
os.chdir(BACKEND_DIR)

import jwt
from fastapi.testclient import TestClient

from app.core.config import settings
from app.crud import user as user_crud
from app.database.session import SessionLocal
from app.main import app


def main() -> int:
    if not settings.JWT_SECRET_KEY:
        print("FAIL: JWT_SECRET_KEY is not configured")
        return 1

    email = f"smoke-{uuid.uuid4().hex}@example.com"
    password = "smoke-password-1"

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/auth/register",
                json={"email": email, "password": password},
            )
            print("register:", "PASS" if response.status_code == 201 else f"FAIL {response.status_code}")

            response = client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": password},
            )
            if response.status_code != 200:
                print("login:", f"FAIL {response.status_code}")
                return 1

            token = response.json()["access_token"]
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
            print("login:", "PASS")
            print("JWT generation:", "PASS")
            print("JWT signature validation:", "PASS")
            print("JWT subject validation:", "PASS" if payload.get("sub") else "FAIL")
            print("JWT expiration validation:", "PASS" if payload.get("exp") else "FAIL")

            headers = {"Authorization": f"Bearer {token}"}
            me = client.get("/api/v1/users/me", headers=headers)
            print(
                "users/me:",
                "PASS" if me.status_code == 200 and me.json()["email"] == email else f"FAIL {me.status_code}",
            )

            missing = client.get("/api/v1/users/me")
            print("users/me without token -> 401:", "PASS" if missing.status_code == 401 else "FAIL")
    finally:
        db = SessionLocal()
        try:
            user = user_crud.get_user_by_email(db, email)
            if user is not None:
                db.delete(user)
                db.commit()
        finally:
            db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
