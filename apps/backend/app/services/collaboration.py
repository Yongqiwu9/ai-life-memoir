import hmac
import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException, NotFoundException
from app.core.rights_auth_provider import RightsAuthProvider, unavailable
from app.crud import collaboration as crud
from app.crud import identity_foundation as identity_crud
from app.models.collaboration import FamilyInvitation, FamilyMembership
from app.models.user import User
from app.schemas.collaboration import InvitationCreate, InvitationRead, MembershipRead
from app.services import command_idempotency as idempotency
from app.services import privacy_policy
from app.services.collaboration_authorization import require_family_actor


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _provider_ready(provider: RightsAuthProvider) -> None:
    if not provider.ready():
        raise unavailable()


def invitation_token_digest(
    provider: RightsAuthProvider, invitation_id: uuid.UUID, token: str
) -> bytes:
    return provider.code_digest(invitation_id, "invitation:" + token)


def _recipient_context(
    provider: RightsAuthProvider, invitation: FamilyInvitation
) -> tuple[str, str]:
    try:
        context = json.loads(provider.decrypt(invitation.recipient_ciphertext))
        kind, channel = context["kind"], context["channel"]
        if kind not in ("email", "phone") or not isinstance(channel, str):
            raise ValueError()
        if not hmac.compare_digest(invitation.recipient_hash, provider.lookup(kind, channel)):
            raise ValueError()
        return kind, channel
    except Exception:  # noqa: BLE001 - provider boundary fails closed
        raise unavailable() from None


def _resolve_known_recipient(
    db: Session, *, kind: str, channel: str, recipient_hash: bytes
) -> uuid.UUID | None:
    contacts = identity_crud.contacts_for_channel(db, kind, recipient_hash)
    effective = [item for item in contacts if item.state == "verified"]
    if not effective:
        return None
    user_ids = {item.user_id for item in effective}
    if len(user_ids) != 1:
        raise AppException(
            "Invitation cannot be created", code="INVALID_INVITATION_RECIPIENT", status_code=409
        )
    user = identity_crud.locked_user(db, next(iter(user_ids)))
    if user is None or user.principal_kind != "account":
        raise AppException(
            "Invitation cannot be created", code="INVALID_INVITATION_RECIPIENT", status_code=409
        )
    if kind == "email" and user.email is not None and user.email.lower() != channel:
        raise AppException(
            "Invitation cannot be created", code="INVALID_INVITATION_RECIPIENT", status_code=409
        )
    return user.id


def _commit(db: Session) -> None:
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


def _invitation_snapshot(invitation: FamilyInvitation) -> idempotency.InvitationResultSnapshot:
    return idempotency.InvitationResultSnapshot.model_validate(invitation)


def _membership_snapshot(membership: FamilyMembership) -> idempotency.MembershipResultSnapshot:
    return idempotency.MembershipResultSnapshot.model_validate(membership)


def _replayed_invitation(record) -> InvitationRead:
    try:
        return InvitationRead.model_validate(record.response_body)
    except (TypeError, ValueError):
        raise AppException(
            "Idempotency result unavailable", code="IDEMPOTENCY_RESULT_UNAVAILABLE", status_code=409
        ) from None


def _replayed_membership(record) -> MembershipRead:
    try:
        return MembershipRead.model_validate(record.response_body)
    except (TypeError, ValueError):
        raise AppException(
            "Idempotency result unavailable", code="IDEMPOTENCY_RESULT_UNAVAILABLE", status_code=409
        ) from None


def create_invitation(
    db: Session,
    *,
    actor: User,
    family_id: uuid.UUID,
    data: InvitationCreate,
    idempotency_key: uuid.UUID,
    provider: RightsAuthProvider,
) -> FamilyInvitation:
    _provider_ready(provider)
    access = require_family_actor(db, actor=actor, family_id=family_id, lock=True)
    channel = data.recipient.get_secret_value()
    try:
        recipient_hash = provider.lookup(data.recipient_kind, channel)
    except Exception:  # noqa: BLE001 - provider boundary fails closed
        db.rollback()
        raise unavailable() from None
    digest = idempotency.safe_request_digest(
        idempotency.invitation_create_request(family_id, data.recipient_kind, recipient_hash)
    )
    record, replay = idempotency.begin(
        db,
        actor_user_id=actor.id,
        operation="family_invitation.create",
        idempotency_key=idempotency_key,
        digest=digest,
    )
    if replay:
        return _replayed_invitation(record)

    now = datetime.now(UTC)
    try:
        recipient_user_id = _resolve_known_recipient(
            db, kind=data.recipient_kind, channel=channel, recipient_hash=recipient_hash
        )
    except AppException:
        db.rollback()
        raise
    except Exception:  # noqa: BLE001 - provider boundary fails closed
        db.rollback()
        raise unavailable() from None
    if recipient_user_id == access.family.owner_id:
        db.rollback()
        raise AppException(
            "Invitation cannot be created", code="INVALID_INVITATION_RECIPIENT", status_code=409
        )
    if recipient_user_id is not None:
        existing = crud.get_family_membership(db, family_id, recipient_user_id, lock=True)
        if existing is not None and existing.state == "active":
            db.rollback()
            raise AppException(
                "Invitation cannot be created", code="MEMBERSHIP_ALREADY_ACTIVE", status_code=409
            )

    try:
        invitation = FamilyInvitation(
            id=uuid.uuid4(),
            family_id=family_id,
            requested_by_user_id=actor.id,
            recipient_hash=recipient_hash,
            recipient_ciphertext=provider.encrypt(
                json.dumps({"kind": data.recipient_kind, "channel": channel}).encode()
            ),
            recipient_user_id=recipient_user_id,
            state="pending_owner" if access.role == "collaborator" else "approved",
            version=1,
        )
        token: str | None = None
        if access.role == "owner":
            window = privacy_policy.invitation_window_seconds(db)
            token = secrets.token_urlsafe(32)
            invitation.approved_by_user_id = actor.id
            invitation.approved_at = now
            invitation.expires_at = now + timedelta(seconds=window)
            invitation.token_digest = invitation_token_digest(provider, invitation.id, token)
    except AppException:
        db.rollback()
        raise
    except Exception:  # noqa: BLE001 - provider boundary fails closed
        db.rollback()
        raise unavailable() from None
    try:
        db.add(invitation)
        db.flush()
    except IntegrityError:
        db.rollback()
        raise AppException(
            "Invitation conflicts with an active invitation",
            code="INVITATION_CONFLICT",
            status_code=409,
        ) from None
    if token is not None:
        try:
            provider.deliver(data.recipient_kind, channel, invitation.id, token)
        except Exception:  # noqa: BLE001 - provider delivery fails closed
            db.rollback()
            raise unavailable() from None
    idempotency.complete(
        record,
        resource_kind="family_invitation",
        resource_id=invitation.id,
        response_status=201,
        snapshot=_invitation_snapshot(invitation),
    )
    _commit(db)
    db.refresh(invitation)
    return invitation


def _owner_invitation(db: Session, *, actor: User, invitation_id: uuid.UUID) -> FamilyInvitation:
    invitation = crud.get_invitation(db, invitation_id, lock=True)
    if invitation is None:
        raise NotFoundException("Invitation not found")
    access = require_family_actor(db, actor=actor, family_id=invitation.family_id, lock=True)
    if access.role != "owner":
        raise AppException("Operation not permitted", code="FORBIDDEN", status_code=403)
    return invitation


def approve_invitation(
    db: Session,
    *,
    actor: User,
    invitation_id: uuid.UUID,
    expected_version: int,
    idempotency_key: uuid.UUID,
    provider: RightsAuthProvider,
) -> FamilyInvitation:
    _provider_ready(provider)
    invitation = _owner_invitation(db, actor=actor, invitation_id=invitation_id)
    record, replay = idempotency.begin(
        db,
        actor_user_id=actor.id,
        operation="family_invitation.approve",
        idempotency_key=idempotency_key,
        digest=idempotency.safe_request_digest(
            idempotency.invitation_approve_request(invitation_id, expected_version)
        ),
    )
    if replay:
        return _replayed_invitation(record)
    if invitation.state != "pending_owner" or invitation.version != expected_version:
        db.rollback()
        raise AppException("Invitation state conflict", code="INVITATION_CONFLICT", status_code=409)
    try:
        kind, channel = _recipient_context(provider, invitation)
        invitation_window = privacy_policy.invitation_window_seconds(db)
    except AppException:
        db.rollback()
        raise
    now = datetime.now(UTC)
    token = secrets.token_urlsafe(32)
    try:
        token_digest = invitation_token_digest(provider, invitation.id, token)
    except Exception:  # noqa: BLE001 - provider boundary fails closed
        db.rollback()
        raise unavailable() from None
    invitation.state = "approved"
    invitation.approved_by_user_id = actor.id
    invitation.approved_at = now
    invitation.expires_at = now + timedelta(seconds=invitation_window)
    invitation.token_digest = token_digest
    invitation.version += 1
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise AppException(
            "Invitation state conflict", code="INVITATION_CONFLICT", status_code=409
        ) from None
    try:
        provider.deliver(kind, channel, invitation.id, token)
    except Exception:  # noqa: BLE001 - provider delivery fails closed
        db.rollback()
        raise unavailable() from None
    idempotency.complete(
        record,
        resource_kind="family_invitation",
        resource_id=invitation.id,
        response_status=200,
        snapshot=_invitation_snapshot(invitation),
    )
    _commit(db)
    db.refresh(invitation)
    return invitation


def transition_invitation(
    db: Session,
    *,
    actor: User,
    invitation_id: uuid.UUID,
    expected_version: int,
    action: str,
    idempotency_key: uuid.UUID,
) -> FamilyInvitation:
    invitation = crud.get_invitation(db, invitation_id, lock=True)
    if invitation is None:
        raise NotFoundException("Invitation not found")
    access = require_family_actor(db, actor=actor, family_id=invitation.family_id, lock=True)
    target = {"reject": "rejected", "cancel": "cancelled", "revoke": "revoked"}[action]
    if action in ("reject", "revoke") and access.role != "owner":
        raise AppException("Operation not permitted", code="FORBIDDEN", status_code=403)
    if action == "cancel" and invitation.requested_by_user_id != actor.id:
        raise AppException("Operation not permitted", code="FORBIDDEN", status_code=403)
    expected_state = "approved" if action == "revoke" else "pending_owner"
    payload_builder = {
        "reject": idempotency.invitation_reject_request,
        "cancel": idempotency.invitation_cancel_request,
        "revoke": idempotency.invitation_revoke_request,
    }[action]
    record, replay = idempotency.begin(
        db,
        actor_user_id=actor.id,
        operation=f"family_invitation.{action}",
        idempotency_key=idempotency_key,
        digest=idempotency.safe_request_digest(payload_builder(invitation_id, expected_version)),
    )
    if replay:
        return _replayed_invitation(record)
    if invitation.state != expected_state or invitation.version != expected_version:
        db.rollback()
        raise AppException("Invitation state conflict", code="INVITATION_CONFLICT", status_code=409)
    invitation.state = target
    invitation.version += 1
    db.flush()
    idempotency.complete(
        record,
        resource_kind="family_invitation",
        resource_id=invitation.id,
        response_status=200,
        snapshot=_invitation_snapshot(invitation),
    )
    _commit(db)
    db.refresh(invitation)
    return invitation


def validate_verification_proof(
    db: Session,
    *,
    actor: User,
    invitation: FamilyInvitation,
    proof: str,
):
    import jwt

    from app.core.security import decode_verification_proof

    try:
        payload = decode_verification_proof(proof)
        subject = uuid.UUID(payload["sub"])
        context_id = uuid.UUID(payload["context_id"])
        challenge_id = uuid.UUID(payload["challenge_id"])
        contact_id = uuid.UUID(payload["contact_id"])
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError, AttributeError):
        raise AppException(
            "Invalid identity verification", code="INVALID_VERIFICATION", status_code=401
        ) from None
    contact = identity_crud.get_contact(db, contact_id)
    challenge = identity_crud.get_challenge(db, challenge_id)
    if (
        actor.principal_kind != "account"
        or subject != actor.id
        or payload.get("principal_kind") != "account"
        or payload.get("token_type") != "verification_proof"
        or payload.get("scope") != ["identity:verify"]
        or payload.get("context_kind") != "invitation_acceptance"
        or context_id != invitation.id
        or type(payload.get("auth_generation")) is not int
        or payload["auth_generation"] != actor.auth_generation
        or contact is None
        or contact.state != "verified"
        or contact.user_id != actor.id
        or challenge is None
        or challenge.state != "consumed"
        or challenge.user_id != actor.id
        or challenge.context_kind != "invitation_acceptance"
        or challenge.context_id != invitation.id
        or challenge.id != challenge_id
        or challenge.channel_hash != contact.lookup_hash
        or not hmac.compare_digest(contact.lookup_hash, invitation.recipient_hash)
    ):
        db.rollback()
        raise AppException(
            "Invalid identity verification", code="INVALID_VERIFICATION", status_code=401
        )
    return contact


def accept_invitation(
    db: Session,
    *,
    actor: User,
    invitation_id: uuid.UUID,
    expected_version: int,
    invitation_token: str,
    verification_proof: str,
    idempotency_key: uuid.UUID,
    provider: RightsAuthProvider,
) -> FamilyMembership:
    _provider_ready(provider)
    invitation = crud.get_invitation(db, invitation_id, lock=True)
    if invitation is None or actor.principal_kind != "account":
        raise AppException(
            "Invalid invitation acceptance", code="INVALID_INVITATION", status_code=401
        )
    try:
        token_fingerprint = idempotency.invitation_token_fingerprint(
            provider, invitation_id, invitation_token
        )
        proof_fingerprint = idempotency.verification_proof_fingerprint(
            provider, invitation_id, verification_proof
        )
    except Exception:  # noqa: BLE001 - provider boundary fails closed
        db.rollback()
        raise unavailable() from None
    record, replay = idempotency.begin(
        db,
        actor_user_id=actor.id,
        operation="family_invitation.accept",
        idempotency_key=idempotency_key,
        digest=idempotency.safe_request_digest(
            idempotency.invitation_accept_request(
                invitation_id,
                expected_version,
                token_fingerprint,
                proof_fingerprint,
            )
        ),
    )
    if replay:
        if record.response_status != 200:
            raise AppException(
                "Invalid invitation acceptance", code="INVALID_INVITATION", status_code=401
            )
        return _replayed_membership(record)
    now = datetime.now(UTC)
    if (
        invitation.state == "approved"
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
            snapshot=idempotency.InvitationErrorSnapshot(),
        )
        _commit(db)
        raise AppException(
            "Invalid invitation acceptance", code="INVALID_INVITATION", status_code=401
        )
    try:
        token_matches = invitation.token_digest is not None and hmac.compare_digest(
            invitation.token_digest,
            invitation_token_digest(provider, invitation.id, invitation_token),
        )
    except Exception:  # noqa: BLE001 - provider boundary fails closed
        db.rollback()
        raise unavailable() from None
    if (
        invitation.state != "approved"
        or invitation.version != expected_version
        or invitation.expires_at is None
        or not token_matches
        or (invitation.recipient_user_id is not None and invitation.recipient_user_id != actor.id)
    ):
        db.rollback()
        raise AppException(
            "Invalid invitation acceptance", code="INVALID_INVITATION", status_code=401
        )
    try:
        validate_verification_proof(
            db, actor=actor, invitation=invitation, proof=verification_proof
        )
    except AppException:
        db.rollback()
        raise
    family = crud.get_family(db, invitation.family_id, lock=True)
    if family is None or family.owner_id == actor.id:
        db.rollback()
        raise AppException(
            "Invalid invitation acceptance", code="INVALID_INVITATION", status_code=401
        )
    membership = crud.get_family_membership(db, family.id, actor.id, lock=True)
    if membership is None:
        membership = FamilyMembership(
            family_id=family.id,
            user_id=actor.id,
            role="collaborator",
            state="active",
            generation=1,
            accepted_invitation_id=invitation.id,
            joined_at=now,
        )
        db.add(membership)
    elif membership.state in ("revoked", "left"):
        membership.state = "active"
        membership.generation += 1
        membership.accepted_invitation_id = invitation.id
        membership.joined_at = now
        membership.ended_at = None
    else:
        db.rollback()
        raise AppException(
            "Membership is already active", code="MEMBERSHIP_ALREADY_ACTIVE", status_code=409
        )
    invitation.state = "accepted"
    invitation.recipient_user_id = actor.id
    invitation.accepted_at = now
    invitation.version += 1
    try:
        db.flush()
        idempotency.complete(
            record,
            resource_kind="family_membership",
            resource_id=membership.id,
            response_status=200,
            snapshot=_membership_snapshot(membership),
        )
        _commit(db)
        db.refresh(membership)
        return membership
    except IntegrityError:
        db.rollback()
        raise AppException(
            "Invitation acceptance conflict", code="INVITATION_CONFLICT", status_code=409
        ) from None


def list_memberships(
    db: Session, *, actor: User, family_id: uuid.UUID, page: int, page_size: int
) -> tuple[list[FamilyMembership], int]:
    require_family_actor(db, actor=actor, family_id=family_id)
    return crud.list_active_memberships(
        db, family_id, offset=(page - 1) * page_size, limit=page_size
    )


def end_membership(
    db: Session,
    *,
    actor: User,
    family_id: uuid.UUID,
    membership_id: uuid.UUID,
    expected_generation: int,
    idempotency_key: uuid.UUID,
) -> FamilyMembership:
    access = require_family_actor(db, actor=actor, family_id=family_id, lock=True)
    membership = crud.get_membership(db, membership_id, lock=True)
    if membership is None or membership.family_id != family_id:
        raise NotFoundException("Membership not found")
    if access.role != "owner" and membership.user_id != actor.id:
        raise AppException("Operation not permitted", code="FORBIDDEN", status_code=403)
    action = "revoke" if access.role == "owner" else "leave"
    payload_builder = (
        idempotency.membership_revoke_request
        if action == "revoke"
        else idempotency.membership_leave_request
    )
    record, replay = idempotency.begin(
        db,
        actor_user_id=actor.id,
        operation=f"family_membership.{action}",
        idempotency_key=idempotency_key,
        digest=idempotency.safe_request_digest(
            payload_builder(family_id, membership_id, expected_generation)
        ),
    )
    if replay:
        return _replayed_membership(record)
    if membership.state != "active" or membership.generation != expected_generation:
        db.rollback()
        raise AppException("Membership state conflict", code="MEMBERSHIP_CONFLICT", status_code=409)
    membership.state = "revoked" if access.role == "owner" else "left"
    membership.generation += 1
    membership.ended_at = datetime.now(UTC)
    db.flush()
    idempotency.complete(
        record,
        resource_kind="family_membership",
        resource_id=membership.id,
        response_status=200,
        snapshot=_membership_snapshot(membership),
    )
    _commit(db)
    db.refresh(membership)
    return membership
