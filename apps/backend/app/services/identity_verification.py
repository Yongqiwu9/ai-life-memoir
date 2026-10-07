import hmac
import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.core.rights_auth_provider import RightsAuthProvider, unavailable
from app.core.security import create_verification_proof
from app.crud import collaboration as collaboration_crud
from app.crud import identity_foundation as crud
from app.crud import interview_participant as participant_crud
from app.crud import user as user_crud
from app.dependencies.participant_actor import ParticipantActor
from app.models.identity_foundation import AuthChallenge, UserContact
from app.models.user import User
from app.services import command_idempotency as idempotency
from app.services.collaboration import invitation_token_digest


def _provider_ready(provider: RightsAuthProvider) -> None:
    if not provider.ready():
        raise unavailable()


def _invalid() -> AppException:
    return AppException(
        "Verification unavailable or invalid", code="INVALID_VERIFICATION", status_code=401
    )


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _recipient_context(provider: RightsAuthProvider, ciphertext: bytes) -> tuple[str, str]:
    try:
        context = json.loads(provider.decrypt(ciphertext))
        kind, channel = context["kind"], context["channel"]
        if kind not in ("email", "phone") or not isinstance(channel, str):
            raise ValueError()
        return kind, channel
    except Exception:  # noqa: BLE001 - provider boundary fails closed
        raise unavailable() from None


def create_invitation_challenge(
    db: Session,
    *,
    actor: User,
    invitation_id: uuid.UUID,
    invitation_token: str,
    idempotency_key: uuid.UUID,
    provider: RightsAuthProvider,
) -> uuid.UUID:
    _provider_ready(provider)
    if actor.principal_kind != "account":
        raise _invalid()
    try:
        token_fingerprint = idempotency.invitation_token_fingerprint(
            provider, invitation_id, invitation_token
        )
    except Exception:  # noqa: BLE001 - provider boundary fails closed
        db.rollback()
        raise unavailable() from None
    record, replay = idempotency.begin(
        db,
        actor_user_id=actor.id,
        operation="identity_verification.invitation_challenge",
        idempotency_key=idempotency_key,
        digest=idempotency.safe_request_digest(
            idempotency.invitation_challenge_request(invitation_id, token_fingerprint)
        ),
    )
    if replay:
        if record.response_status != 202 or record.resource_id is None:
            raise _invalid()
        return record.resource_id
    invitation = collaboration_crud.get_invitation(db, invitation_id, lock=True)
    now = datetime.now(UTC)
    if (
        invitation is not None
        and invitation.state == "approved"
        and invitation.expires_at is not None
        and _utc(invitation.expires_at) <= now
    ):
        invitation.state = "expired"
        invitation.version += 1
        idempotency.complete(
            record,
            resource_kind="family_invitation",
            resource_id=invitation.id,
            response_status=401,
            snapshot=idempotency.VerificationErrorSnapshot(),
        )
        db.commit()
        raise _invalid()
    if (
        invitation is None
        or invitation.state != "approved"
        or invitation.expires_at is None
        or invitation.token_digest is None
        or not hmac.compare_digest(
            invitation.token_digest,
            invitation_token_digest(provider, invitation.id, invitation_token),
        )
        or (invitation.recipient_user_id is not None and invitation.recipient_user_id != actor.id)
    ):
        db.rollback()
        raise _invalid()
    try:
        kind, channel = _recipient_context(provider, invitation.recipient_ciphertext)
    except AppException:
        db.rollback()
        raise
    channel_hash = provider.lookup(kind, channel)
    if not hmac.compare_digest(channel_hash, invitation.recipient_hash):
        db.rollback()
        raise _invalid()
    if kind == "email":
        legacy = user_crud.get_user_by_email(db, channel)
        if legacy is not None and legacy.id != actor.id:
            db.rollback()
            raise _invalid()
    contacts = crud.contacts_for_channel(db, kind, channel_hash)
    if any(contact.user_id != actor.id for contact in contacts):
        db.rollback()
        raise _invalid()
    expires_at = now + timedelta(seconds=provider.configuration.challenge_ttl.seconds)
    if not provider.reserve_challenge(channel_hash, now, expires_at):
        db.rollback()
        raise AppException(
            "Verification rate limited", code="VERIFICATION_RATE_LIMITED", status_code=429
        )
    challenge_id, code = uuid.uuid4(), secrets.token_urlsafe(24)
    context = {
        "kind": kind,
        "channel": channel,
        "attempt_limit": provider.configuration.attempt_limit,
        "proof_ttl": provider.configuration.token_ttl.seconds,
    }
    challenge = AuthChallenge(
        id=challenge_id,
        user_id=actor.id,
        context_kind="invitation_acceptance",
        context_id=invitation.id,
        channel_ciphertext=provider.encrypt(json.dumps(context).encode()),
        channel_hash=channel_hash,
        code_digest=provider.code_digest(challenge_id, code),
        state="pending",
        expires_at=expires_at,
        attempt_count=0,
    )
    try:
        db.add(challenge)
        db.flush()
        provider.deliver(kind, channel, challenge.id, code)
        idempotency.complete(
            record,
            resource_kind="auth_challenge",
            resource_id=challenge.id,
            response_status=202,
            snapshot=idempotency.ChallengeAcceptedSnapshot(),
        )
        db.commit()
        return challenge.id
    except AppException:
        db.rollback()
        raise
    except Exception:  # noqa: BLE001 - provider boundary fails closed
        db.rollback()
        raise unavailable() from None


def _resolve_account_contact(
    db: Session,
    *,
    actor: User,
    kind: str,
    channel: str,
    channel_hash: bytes,
    provider: RightsAuthProvider,
    now: datetime,
) -> UserContact:
    contacts = crud.contacts_for_channel(db, kind, channel_hash)
    if any(contact.user_id != actor.id for contact in contacts):
        raise _invalid()
    if kind == "email":
        legacy = user_crud.get_user_by_email(db, channel)
        if legacy is not None and legacy.id != actor.id:
            raise _invalid()
    verified = [contact for contact in contacts if contact.state == "verified"]
    if len(verified) == 1:
        return verified[0]
    if len(verified) > 1:
        raise _invalid()
    pending = [contact for contact in contacts if contact.state == "pending"]
    if pending:
        contact = pending[0]
        contact.state = "verified"
        contact.verified_at = now
        contact.revoked_at = None
        return contact
    contact = UserContact(
        user_id=actor.id,
        kind=kind,
        value_ciphertext=provider.encrypt(channel.encode()),
        lookup_hash=channel_hash,
        state="verified",
        verified_at=now,
    )
    db.add(contact)
    db.flush()
    return contact


def verify_invitation_challenge(
    db: Session,
    *,
    actor: User,
    challenge_id: uuid.UUID,
    code: str,
    idempotency_key: uuid.UUID,
    provider: RightsAuthProvider,
) -> str:
    _provider_ready(provider)
    if actor.principal_kind != "account":
        raise _invalid()
    try:
        code_fingerprint = idempotency.verification_code_fingerprint(provider, challenge_id, code)
    except Exception:  # noqa: BLE001 - provider boundary fails closed
        db.rollback()
        raise unavailable() from None
    record, replay = idempotency.begin(
        db,
        actor_user_id=actor.id,
        operation="identity_verification.invitation_verify",
        idempotency_key=idempotency_key,
        digest=idempotency.safe_request_digest(
            idempotency.invitation_verify_request(challenge_id, code_fingerprint)
        ),
    )
    if replay:
        if record.response_status != 200:
            raise _invalid()
        challenge = crud.get_challenge(db, challenge_id)
        try:
            snapshot = idempotency.VerificationResultSnapshot.model_validate(record.response_body)
        except (TypeError, ValueError):
            raise _invalid() from None
        if (
            challenge is None
            or challenge.state != "consumed"
            or snapshot.context_id != challenge.context_id
            or snapshot.expires_at <= datetime.now(UTC)
        ):
            raise _invalid()
        return create_verification_proof(
            subject=str(actor.id),
            auth_generation=actor.auth_generation,
            context_kind="invitation_acceptance",
            context_id=str(challenge.context_id),
            challenge_id=str(challenge.id),
            contact_id=str(snapshot.contact_id),
            expires_at=snapshot.expires_at,
            issued_at=snapshot.issued_at,
        )
    challenge = crud.get_challenge(db, challenge_id, lock=True)
    now = datetime.now(UTC)
    if (
        challenge is None
        or challenge.context_kind != "invitation_acceptance"
        or challenge.user_id != actor.id
        or challenge.state != "pending"
    ):
        provider.code_digest(challenge_id, code)
        db.rollback()
        raise _invalid()
    if _utc(challenge.expires_at) <= now:
        challenge.state = "expired"
        idempotency.complete(
            record,
            resource_kind="auth_challenge",
            resource_id=challenge.id,
            response_status=401,
            snapshot=idempotency.VerificationErrorSnapshot(),
        )
        db.commit()
        raise _invalid()
    committed_error = False
    try:
        context = json.loads(provider.decrypt(challenge.channel_ciphertext))
        limit = context["attempt_limit"]
        proof_ttl = context["proof_ttl"]
        if type(limit) is not int or limit <= 0 or type(proof_ttl) is not int or proof_ttl <= 0:
            raise ValueError()
        valid = hmac.compare_digest(challenge.code_digest, provider.code_digest(challenge.id, code))
        if not valid:
            challenge.attempt_count += 1
            if challenge.attempt_count >= limit:
                challenge.state = "locked"
            idempotency.complete(
                record,
                resource_kind="auth_challenge",
                resource_id=challenge.id,
                response_status=401,
                snapshot=idempotency.VerificationErrorSnapshot(),
            )
            db.commit()
            committed_error = True
            raise _invalid()
        if not hmac.compare_digest(
            challenge.channel_hash, provider.lookup(context["kind"], context["channel"])
        ):
            raise _invalid()
        contact = _resolve_account_contact(
            db,
            actor=actor,
            kind=context["kind"],
            channel=context["channel"],
            channel_hash=challenge.channel_hash,
            provider=provider,
            now=now,
        )
        expires_at = now + timedelta(seconds=proof_ttl)
        challenge.state = "consumed"
        challenge.consumed_at = now
        challenge.user_id = actor.id
        idempotency.complete(
            record,
            resource_kind="auth_challenge",
            resource_id=challenge.id,
            response_status=200,
            snapshot=idempotency.VerificationResultSnapshot(
                issued_at=now,
                expires_at=expires_at,
                context_id=challenge.context_id,
                contact_id=contact.id,
            ),
        )
        db.commit()
        return create_verification_proof(
            subject=str(actor.id),
            auth_generation=actor.auth_generation,
            context_kind="invitation_acceptance",
            context_id=str(challenge.context_id),
            challenge_id=str(challenge.id),
            contact_id=str(contact.id),
            expires_at=expires_at,
            issued_at=now,
        )
    except AppException:
        if not committed_error:
            db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise _invalid() from None
    except Exception:  # noqa: BLE001 - provider boundary fails closed
        db.rollback()
        raise unavailable() from None


def create_participant_challenge(
    db: Session,
    *,
    actor: ParticipantActor,
    participant_id: uuid.UUID,
    contact_kind: str | None,
    contact_value: str | None,
    idempotency_key: uuid.UUID,
    provider: RightsAuthProvider,
) -> uuid.UUID:
    _provider_ready(provider)
    participant = participant_crud.get_participant(db, participant_id, lock=True)
    if participant is None or participant.state != "proposed" or participant.user_id is not None:
        db.rollback()
        raise _invalid()
    try:
        if actor.authentication == "rights":
            if contact_kind is not None or contact_value is not None or actor.contact_id is None:
                raise _invalid()
            contact = crud.get_contact(db, actor.contact_id)
            if contact is None or contact.user_id != actor.user.id or contact.state != "verified":
                raise _invalid()
            contact_kind = contact.kind
            contact_value = provider.decrypt(contact.value_ciphertext).decode()
            if not hmac.compare_digest(
                contact.lookup_hash, provider.lookup(contact_kind, contact_value)
            ):
                raise _invalid()
            contact_fingerprint = None
        else:
            if contact_kind is None or contact_value is None:
                raise _invalid()
            contact_fingerprint = idempotency.participant_contact_fingerprint(
                provider, participant_id, f"{contact_kind}:{contact_value}"
            )
        channel_hash = provider.lookup(contact_kind, contact_value)
    except AppException:
        db.rollback()
        raise
    except Exception:  # noqa: BLE001
        db.rollback()
        raise unavailable() from None
    record, replay = idempotency.begin(
        db,
        actor_user_id=actor.user.id,
        operation="identity_verification.participant_challenge",
        idempotency_key=idempotency_key,
        digest=idempotency.safe_request_digest(
            idempotency.participant_challenge_request(participant_id, contact_fingerprint)
        ),
    )
    if replay:
        if record.response_status != 202 or record.resource_id is None:
            raise _invalid()
        return record.resource_id
    contacts = crud.contacts_for_channel(db, contact_kind, channel_hash)
    if any(item.user_id != actor.user.id for item in contacts):
        db.rollback()
        raise _invalid()
    if contact_kind == "email":
        legacy = user_crud.get_user_by_email(db, contact_value)
        if legacy is not None and legacy.id != actor.user.id:
            db.rollback()
            raise _invalid()
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=provider.configuration.challenge_ttl.seconds)
    if not provider.reserve_challenge(channel_hash, now, expires_at):
        db.rollback()
        raise AppException(
            "Verification rate limited", code="VERIFICATION_RATE_LIMITED", status_code=429
        )
    challenge_id, code = uuid.uuid4(), secrets.token_urlsafe(24)
    context = {
        "kind": contact_kind,
        "channel": contact_value,
        "attempt_limit": provider.configuration.attempt_limit,
        "proof_ttl": provider.configuration.token_ttl.seconds,
    }
    challenge = AuthChallenge(
        id=challenge_id,
        user_id=actor.user.id,
        context_kind="participant_confirmation",
        context_id=participant.id,
        channel_ciphertext=provider.encrypt(json.dumps(context).encode()),
        channel_hash=channel_hash,
        code_digest=provider.code_digest(challenge_id, code),
        state="pending",
        expires_at=expires_at,
        attempt_count=0,
    )
    try:
        db.add(challenge)
        db.flush()
        provider.deliver(contact_kind, contact_value, challenge.id, code)
        idempotency.complete(
            record,
            resource_kind="auth_challenge",
            resource_id=challenge.id,
            response_status=202,
            snapshot=idempotency.ChallengeAcceptedSnapshot(),
        )
        db.commit()
        return challenge.id
    except AppException:
        db.rollback()
        raise
    except Exception:  # noqa: BLE001
        db.rollback()
        raise unavailable() from None


def verify_participant_challenge(
    db: Session,
    *,
    actor: ParticipantActor,
    challenge_id: uuid.UUID,
    code: str,
    idempotency_key: uuid.UUID,
    provider: RightsAuthProvider,
) -> str:
    _provider_ready(provider)
    try:
        code_fingerprint = idempotency.verification_code_fingerprint(provider, challenge_id, code)
    except Exception:  # noqa: BLE001 - provider boundary fails closed
        raise unavailable() from None
    record, replay = idempotency.begin(
        db,
        actor_user_id=actor.user.id,
        operation="identity_verification.participant_verify",
        idempotency_key=idempotency_key,
        digest=idempotency.safe_request_digest(
            idempotency.participant_verify_request(challenge_id, code_fingerprint)
        ),
    )
    if replay:
        if record.response_status != 200:
            raise _invalid()
        challenge = crud.get_challenge(db, challenge_id)
        try:
            snapshot = idempotency.VerificationResultSnapshot.model_validate(record.response_body)
        except (TypeError, ValueError):
            raise _invalid() from None
        if (
            challenge is None
            or challenge.state != "consumed"
            or snapshot.expires_at <= datetime.now(UTC)
        ):
            raise _invalid()
        return create_verification_proof(
            subject=str(actor.user.id),
            principal_kind=actor.user.principal_kind,
            auth_generation=actor.user.auth_generation,
            context_kind="participant_confirmation",
            context_id=str(challenge.context_id),
            challenge_id=str(challenge.id),
            contact_id=str(snapshot.contact_id),
            expires_at=snapshot.expires_at,
            issued_at=snapshot.issued_at,
        )
    challenge = crud.get_challenge(db, challenge_id, lock=True)
    now = datetime.now(UTC)
    if (
        challenge is None
        or challenge.context_kind != "participant_confirmation"
        or challenge.user_id != actor.user.id
        or challenge.state != "pending"
    ):
        provider.code_digest(challenge_id, code)
        db.rollback()
        raise _invalid()
    if _utc(challenge.expires_at) <= now:
        challenge.state = "expired"
        idempotency.complete(
            record,
            resource_kind="auth_challenge",
            resource_id=challenge.id,
            response_status=401,
            snapshot=idempotency.VerificationErrorSnapshot(),
        )
        db.commit()
        raise _invalid()
    committed_error = False
    try:
        context = json.loads(provider.decrypt(challenge.channel_ciphertext))
        limit, proof_ttl = context["attempt_limit"], context["proof_ttl"]
        if type(limit) is not int or limit <= 0 or type(proof_ttl) is not int or proof_ttl <= 0:
            raise ValueError()
        if not hmac.compare_digest(challenge.code_digest, provider.code_digest(challenge.id, code)):
            challenge.attempt_count += 1
            if challenge.attempt_count >= limit:
                challenge.state = "locked"
            idempotency.complete(
                record,
                resource_kind="auth_challenge",
                resource_id=challenge.id,
                response_status=401,
                snapshot=idempotency.VerificationErrorSnapshot(),
            )
            db.commit()
            committed_error = True
            raise _invalid()
        if not hmac.compare_digest(
            challenge.channel_hash, provider.lookup(context["kind"], context["channel"])
        ):
            raise _invalid()
        if actor.authentication == "rights":
            contact = crud.get_contact(db, actor.contact_id)
            if (
                contact is None
                or contact.user_id != actor.user.id
                or contact.state != "verified"
                or not hmac.compare_digest(contact.lookup_hash, challenge.channel_hash)
            ):
                raise _invalid()
        else:
            contact = _resolve_account_contact(
                db,
                actor=actor.user,
                kind=context["kind"],
                channel=context["channel"],
                channel_hash=challenge.channel_hash,
                provider=provider,
                now=now,
            )
        expires_at = now + timedelta(seconds=proof_ttl)
        challenge.state = "consumed"
        challenge.consumed_at = now
        idempotency.complete(
            record,
            resource_kind="auth_challenge",
            resource_id=challenge.id,
            response_status=200,
            snapshot=idempotency.VerificationResultSnapshot(
                issued_at=now,
                expires_at=expires_at,
                context_id=challenge.context_id,
                contact_id=contact.id,
            ),
        )
        db.commit()
        return create_verification_proof(
            subject=str(actor.user.id),
            principal_kind=actor.user.principal_kind,
            auth_generation=actor.user.auth_generation,
            context_kind="participant_confirmation",
            context_id=str(challenge.context_id),
            challenge_id=str(challenge.id),
            contact_id=str(contact.id),
            expires_at=expires_at,
            issued_at=now,
        )
    except AppException:
        if not committed_error:
            db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise _invalid() from None
    except Exception:  # noqa: BLE001
        db.rollback()
        raise unavailable() from None
