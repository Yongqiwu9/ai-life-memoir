from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str, *, auth_generation: int = 1) -> str:
    if not settings.JWT_SECRET_KEY:
        raise RuntimeError("JWT_SECRET_KEY is not configured")
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": expires_at,
        "principal_kind": "account",
        "auth_generation": auth_generation,
        "token_type": "account",
        "scope": ["account:api"],
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    if not settings.JWT_SECRET_KEY:
        raise RuntimeError("JWT_SECRET_KEY is not configured")
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        options={
            "require": [
                "sub",
                "iat",
                "exp",
                "token_type",
                "principal_kind",
                "auth_generation",
                "scope",
            ]
        },
    )


def create_rights_token(
    *,
    subject: str,
    principal_kind: str,
    auth_generation: int,
    challenge_id: str,
    contact_id: str,
    lifetime_seconds: int,
) -> str:
    if not settings.JWT_SECRET_KEY:
        raise RuntimeError("JWT_SECRET_KEY is not configured")
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "principal_kind": principal_kind,
        "auth_generation": auth_generation,
        "token_type": "rights",
        "scope": ["rights:identity"],
        "iat": now,
        "exp": now + timedelta(seconds=lifetime_seconds),
        "aud": "memoir-rights",
        "iss": "memoir-backend",
        "verification_ref": challenge_id,
        "contact_id": contact_id,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_rights_token(token: str) -> dict:
    if not settings.JWT_SECRET_KEY:
        raise RuntimeError("JWT_SECRET_KEY is not configured")
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        audience="memoir-rights",
        issuer="memoir-backend",
        options={
            "require": [
                "sub",
                "iat",
                "exp",
                "aud",
                "iss",
                "token_type",
                "principal_kind",
                "auth_generation",
                "scope",
                "verification_ref",
                "contact_id",
            ]
        },
    )


def create_verification_proof(
    *,
    subject: str,
    auth_generation: int,
    context_kind: str,
    context_id: str,
    challenge_id: str,
    contact_id: str,
    expires_at: datetime,
    issued_at: datetime | None = None,
) -> str:
    if not settings.JWT_SECRET_KEY:
        raise RuntimeError("JWT_SECRET_KEY is not configured")
    now = issued_at or datetime.now(UTC)
    payload = {
        "sub": subject,
        "principal_kind": "account",
        "auth_generation": auth_generation,
        "token_type": "verification_proof",
        "scope": ["identity:verify"],
        "context_kind": context_kind,
        "context_id": context_id,
        "challenge_id": challenge_id,
        "contact_id": contact_id,
        "iat": now,
        "exp": expires_at,
        "aud": "memoir-identity-verification",
        "iss": "memoir-backend",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_verification_proof(token: str) -> dict:
    if not settings.JWT_SECRET_KEY:
        raise RuntimeError("JWT_SECRET_KEY is not configured")
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        audience="memoir-identity-verification",
        issuer="memoir-backend",
        options={
            "require": [
                "sub",
                "principal_kind",
                "auth_generation",
                "token_type",
                "scope",
                "context_kind",
                "context_id",
                "challenge_id",
                "contact_id",
                "iat",
                "exp",
                "aud",
                "iss",
            ]
        },
    )
