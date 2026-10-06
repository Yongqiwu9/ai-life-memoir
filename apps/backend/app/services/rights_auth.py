import hmac
import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.core.rights_auth_provider import RightsAuthProvider, unavailable
from app.core.security import create_rights_token
from app.crud import identity_foundation as crud
from app.crud import user as user_crud
from app.models.identity_foundation import AuthChallenge, UserContact
from app.models.user import User
from app.schemas.rights_auth import ChallengeCreate


def invalid_verification() -> AppException:
    return AppException(
        "Verification unavailable or invalid", code="INVALID_VERIFICATION", status_code=401
    )


def _utc(value: datetime) -> datetime:
    # SQLite fast tests lose timezone metadata; PostgreSQL stores TIMESTAMPTZ.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _provider_ready(provider: RightsAuthProvider) -> None:
    if not provider.ready():
        raise unavailable()


def create_challenge(db: Session, payload: ChallengeCreate, provider: RightsAuthProvider):
    _provider_ready(provider)
    channel = payload.channel.get_secret_value()
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=provider.configuration.challenge_ttl.seconds)
    challenge_id, code = uuid.uuid4(), secrets.token_urlsafe(24)
    try:
        channel_hash = provider.lookup(payload.kind, channel)
        if not provider.reserve_challenge(channel_hash, now, expires_at):
            raise AppException(
                "Verification rate limited", code="VERIFICATION_RATE_LIMITED", status_code=429
            )
        context = {
            "kind": payload.kind,
            "channel": channel,
            "attempt_limit": provider.configuration.attempt_limit,
            "token_ttl": provider.configuration.token_ttl.seconds,
        }
        challenge = AuthChallenge(
            id=challenge_id,
            user_id=None,
            context_kind="rights_auth",
            context_id=None,
            channel_ciphertext=provider.encrypt(json.dumps(context).encode()),
            channel_hash=channel_hash,
            code_digest=provider.code_digest(challenge_id, code),
            state="pending",
            expires_at=expires_at,
            attempt_count=0,
        )
        crud.add_and_flush(db, challenge)
        db.commit()
        provider.deliver(payload.kind, channel, challenge_id, code)
    except AppException:
        db.rollback()
        raise
    except Exception:  # noqa: BLE001 - untrusted provider/DB failures must not expose PII
        db.rollback()
        existing = crud.get_challenge(db, challenge_id)
        if existing is not None and existing.state == "pending":
            crud.transition_challenge(
                db, challenge_id, state="pending", attempts=0, values={"state": "expired"}
            )
            db.commit()
        raise unavailable() from None
    return challenge_id


def _resolve_contact(
    db: Session,
    kind: str,
    channel: str,
    channel_hash: bytes,
    provider: RightsAuthProvider,
    now: datetime,
):
    contacts = crud.contacts_for_channel(db, kind, channel_hash)
    effective = [contact for contact in contacts if contact.state == "verified"]
    if len(effective) == 1 and all(contact.user_id == effective[0].user_id for contact in contacts):
        contact = effective[0]
        user = crud.locked_user(db, contact.user_id)
        if user is None or user.principal_kind not in ("account", "rights_only"):
            raise invalid_verification()
        if kind == "email":
            legacy = user_crud.get_user_by_email(db, channel)
            if legacy is not None and legacy.id != user.id:
                raise invalid_verification()
        return user, contact
    # A revoked/pending/legacy channel is not an implicit identity recovery path.
    if contacts or (kind == "email" and user_crud.get_user_by_email(db, channel) is not None):
        raise invalid_verification()
    user = crud.add_and_flush(
        db,
        User(
            principal_kind="rights_only",
            auth_generation=1,
            email=None,
            password_hash=None,
            is_active=True,
        ),
    )
    contact = crud.add_and_flush(
        db,
        UserContact(
            user_id=user.id,
            kind=kind,
            value_ciphertext=provider.encrypt(channel.encode()),
            lookup_hash=channel_hash,
            state="verified",
            verified_at=now,
        ),
    )
    return user, contact


def verify_challenge(
    db: Session, challenge_id: uuid.UUID, code: str, provider: RightsAuthProvider
) -> str:
    _provider_ready(provider)
    challenge = crud.get_challenge(db, challenge_id, lock=True)
    now = datetime.now(UTC)
    if challenge is None or challenge.context_kind != "rights_auth" or challenge.state != "pending":
        # Exercise the digest path even for an unknown receipt without exposing identity.
        provider.code_digest(challenge_id, code)
        raise invalid_verification()
    if _utc(challenge.expires_at) <= now:
        crud.transition_challenge(
            db,
            challenge_id,
            state="pending",
            attempts=challenge.attempt_count,
            values={"state": "expired"},
        )
        db.commit()
        raise invalid_verification()
    try:
        context = json.loads(provider.decrypt(challenge.channel_ciphertext))
        limit = context["attempt_limit"]
        if type(limit) is not int or limit <= 0:
            raise ValueError()
        valid = hmac.compare_digest(challenge.code_digest, provider.code_digest(challenge.id, code))
        if not valid:
            attempts = challenge.attempt_count + 1
            crud.transition_challenge(
                db,
                challenge.id,
                state="pending",
                attempts=challenge.attempt_count,
                values={
                    "attempt_count": attempts,
                    "state": "locked" if attempts >= limit else "pending",
                },
            )
            db.commit()
            raise invalid_verification()
        if not crud.transition_challenge(
            db,
            challenge.id,
            state="pending",
            attempts=challenge.attempt_count,
            values={"state": "verified"},
        ):
            db.rollback()
            raise invalid_verification()
        if not hmac.compare_digest(
            challenge.channel_hash, provider.lookup(context["kind"], context["channel"])
        ):
            raise invalid_verification()
        user, contact = _resolve_contact(
            db, context["kind"], context["channel"], challenge.channel_hash, provider, now
        )
        token = create_rights_token(
            subject=str(user.id),
            principal_kind=user.principal_kind,
            auth_generation=user.auth_generation,
            challenge_id=str(challenge.id),
            contact_id=str(contact.id),
            lifetime_seconds=context["token_ttl"],
        )
        if not crud.transition_challenge(
            db,
            challenge.id,
            state="verified",
            attempts=challenge.attempt_count,
            values={"state": "consumed", "consumed_at": now, "user_id": user.id},
        ):
            raise invalid_verification()
        db.commit()
        db.expire(challenge)
        return token
    except AppException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise invalid_verification() from None
    except Exception:  # noqa: BLE001 - sanitize provider failures at this security boundary
        db.rollback()
        raise unavailable() from None
