import hashlib
import hmac
import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.core.rights_auth_provider import RightsAuthProvider
from app.crud import collaboration as crud
from app.models.collaboration import CommandIdempotencyRecord


class IdempotencyResultSnapshot(BaseModel):
    """Base type for explicitly approved, non-sensitive replay snapshots."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class InvitationResultSnapshot(IdempotencyResultSnapshot):
    id: uuid.UUID
    family_id: uuid.UUID
    requested_by_user_id: uuid.UUID
    recipient_user_id: uuid.UUID | None
    approved_by_user_id: uuid.UUID | None
    state: Literal[
        "pending_owner", "approved", "accepted", "rejected", "cancelled", "revoked", "expired"
    ]
    version: int
    approved_at: datetime | None
    accepted_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MembershipResultSnapshot(IdempotencyResultSnapshot):
    id: uuid.UUID
    family_id: uuid.UUID
    user_id: uuid.UUID
    role: Literal["collaborator"]
    state: Literal["active", "revoked", "left"]
    generation: int
    joined_at: datetime
    ended_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ChallengeAcceptedSnapshot(IdempotencyResultSnapshot):
    status: Literal["accepted"] = "accepted"


class VerificationErrorSnapshot(IdempotencyResultSnapshot):
    error_code: Literal["INVALID_VERIFICATION"] = "INVALID_VERIFICATION"


class InvitationErrorSnapshot(IdempotencyResultSnapshot):
    error_code: Literal["INVALID_INVITATION"] = "INVALID_INVITATION"


class VerificationResultSnapshot(IdempotencyResultSnapshot):
    issued_at: datetime
    expires_at: datetime
    context_id: uuid.UUID
    contact_id: uuid.UUID


class ParticipantResultSnapshot(IdempotencyResultSnapshot):
    id: uuid.UUID
    roles: Literal["speaker"]
    state: Literal["proposed", "verified", "inactive", "disputed"]
    eligibility_state: Literal["unknown", "eligible", "ineligible"]
    verified_at: datetime | None
    adult_declaration_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


_ALLOWED_SNAPSHOTS: dict[str, tuple[type[IdempotencyResultSnapshot], ...]] = {
    "family_invitation.create": (InvitationResultSnapshot,),
    "family_invitation.approve": (InvitationResultSnapshot,),
    "family_invitation.reject": (InvitationResultSnapshot,),
    "family_invitation.cancel": (InvitationResultSnapshot,),
    "family_invitation.accept": (MembershipResultSnapshot, InvitationErrorSnapshot),
    "family_invitation.revoke": (InvitationResultSnapshot,),
    "family_membership.revoke": (MembershipResultSnapshot,),
    "family_membership.leave": (MembershipResultSnapshot,),
    "identity_verification.invitation_challenge": (
        ChallengeAcceptedSnapshot,
        VerificationErrorSnapshot,
    ),
    "identity_verification.invitation_verify": (
        VerificationResultSnapshot,
        VerificationErrorSnapshot,
    ),
    "identity_verification.participant_challenge": (
        ChallengeAcceptedSnapshot,
        VerificationErrorSnapshot,
    ),
    "identity_verification.participant_verify": (
        VerificationResultSnapshot,
        VerificationErrorSnapshot,
    ),
    "interview_participant.propose": (ParticipantResultSnapshot,),
    "interview_participant.confirm": (ParticipantResultSnapshot,),
    "interview_participant.inactivate": (ParticipantResultSnapshot,),
}


def canonical_request_bytes(payload: Mapping[str, object]) -> bytes:
    """Serialize an explicitly constructed, non-sensitive request payload."""

    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode()


def safe_request_digest(payload: Mapping[str, object]) -> bytes:
    return hashlib.sha256(canonical_request_bytes(payload)).digest()


def _fingerprint_hex(value: bytes) -> str:
    if len(value) != hashlib.sha256().digest_size:
        raise ValueError("A SHA-256-sized keyed fingerprint is required")
    return value.hex()


def _provider_fingerprint(
    provider: RightsAuthProvider,
    *,
    binding_id: uuid.UUID,
    domain: Literal[
        "idempotency:invitation-token:v1",
        "idempotency:verification-code:v1",
        "idempotency:verification-proof:v1",
        "idempotency:participant-contact:v1",
    ],
    value: str,
) -> bytes:
    return provider.code_digest(binding_id, f"{domain}\x00{value}")


def invitation_token_fingerprint(
    provider: RightsAuthProvider, invitation_id: uuid.UUID, token: str
) -> bytes:
    return _provider_fingerprint(
        provider,
        binding_id=invitation_id,
        domain="idempotency:invitation-token:v1",
        value=token,
    )


def verification_code_fingerprint(
    provider: RightsAuthProvider, challenge_id: uuid.UUID, code: str
) -> bytes:
    return _provider_fingerprint(
        provider,
        binding_id=challenge_id,
        domain="idempotency:verification-code:v1",
        value=code,
    )


def verification_proof_fingerprint(
    provider: RightsAuthProvider, invitation_id: uuid.UUID, proof: str
) -> bytes:
    return _provider_fingerprint(
        provider,
        binding_id=invitation_id,
        domain="idempotency:verification-proof:v1",
        value=proof,
    )


def participant_contact_fingerprint(
    provider: RightsAuthProvider, participant_id: uuid.UUID, value: str
) -> bytes:
    return _provider_fingerprint(
        provider,
        binding_id=participant_id,
        domain="idempotency:participant-contact:v1",
        value=value,
    )


def invitation_create_request(
    family_id: uuid.UUID, recipient_kind: str, recipient_fingerprint: bytes
) -> dict[str, object]:
    return {
        "family_id": str(family_id),
        "recipient_kind": recipient_kind,
        "recipient_fingerprint_v1": _fingerprint_hex(recipient_fingerprint),
    }


def invitation_approve_request(
    invitation_id: uuid.UUID, expected_version: int
) -> dict[str, object]:
    return {"invitation_id": str(invitation_id), "expected_version": expected_version}


def invitation_reject_request(invitation_id: uuid.UUID, expected_version: int) -> dict[str, object]:
    return {"invitation_id": str(invitation_id), "expected_version": expected_version}


def invitation_cancel_request(invitation_id: uuid.UUID, expected_version: int) -> dict[str, object]:
    return {"invitation_id": str(invitation_id), "expected_version": expected_version}


def invitation_revoke_request(invitation_id: uuid.UUID, expected_version: int) -> dict[str, object]:
    return {"invitation_id": str(invitation_id), "expected_version": expected_version}


def invitation_accept_request(
    invitation_id: uuid.UUID,
    expected_version: int,
    token_fingerprint: bytes,
    proof_fingerprint: bytes,
) -> dict[str, object]:
    return {
        "invitation_id": str(invitation_id),
        "expected_version": expected_version,
        "invitation_token_fingerprint_v1": _fingerprint_hex(token_fingerprint),
        "verification_proof_fingerprint_v1": _fingerprint_hex(proof_fingerprint),
    }


def membership_revoke_request(
    family_id: uuid.UUID, membership_id: uuid.UUID, expected_generation: int
) -> dict[str, object]:
    return {
        "family_id": str(family_id),
        "membership_id": str(membership_id),
        "expected_generation": expected_generation,
    }


def membership_leave_request(
    family_id: uuid.UUID, membership_id: uuid.UUID, expected_generation: int
) -> dict[str, object]:
    return {
        "family_id": str(family_id),
        "membership_id": str(membership_id),
        "expected_generation": expected_generation,
    }


def invitation_challenge_request(
    invitation_id: uuid.UUID, token_fingerprint: bytes
) -> dict[str, object]:
    return {
        "invitation_id": str(invitation_id),
        "invitation_token_fingerprint_v1": _fingerprint_hex(token_fingerprint),
    }


def invitation_verify_request(
    challenge_id: uuid.UUID, code_fingerprint: bytes
) -> dict[str, object]:
    return {
        "challenge_id": str(challenge_id),
        "verification_code_fingerprint_v1": _fingerprint_hex(code_fingerprint),
    }


def participant_propose_request(
    interview_id: uuid.UUID, family_member_id: uuid.UUID | None, roles: str
) -> dict[str, object]:
    return {
        "interview_id": str(interview_id),
        "family_member_id": str(family_member_id) if family_member_id else None,
        "roles": roles,
    }


def participant_challenge_request(
    participant_id: uuid.UUID, contact_fingerprint: bytes | None
) -> dict[str, object]:
    return {
        "participant_id": str(participant_id),
        "contact_fingerprint_v1": (
            _fingerprint_hex(contact_fingerprint) if contact_fingerprint else None
        ),
    }


def participant_verify_request(
    challenge_id: uuid.UUID, code_fingerprint: bytes
) -> dict[str, object]:
    return {
        "challenge_id": str(challenge_id),
        "verification_code_fingerprint_v1": _fingerprint_hex(code_fingerprint),
    }


def participant_confirm_request(
    participant_id: uuid.UUID,
    expected_version: int,
    proof_fingerprint: bytes,
    adult_autonomous_decision: bool,
) -> dict[str, object]:
    return {
        "participant_id": str(participant_id),
        "expected_version": expected_version,
        "verification_proof_fingerprint_v1": _fingerprint_hex(proof_fingerprint),
        "adult_autonomous_decision": adult_autonomous_decision,
    }


def participant_inactivate_request(
    participant_id: uuid.UUID, expected_version: int
) -> dict[str, object]:
    return {"participant_id": str(participant_id), "expected_version": expected_version}


def begin(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    operation: str,
    idempotency_key: uuid.UUID,
    digest: bytes,
) -> tuple[CommandIdempotencyRecord, bool]:
    existing = crud.find_idempotency(
        db,
        actor_user_id=actor_user_id,
        operation=operation,
        idempotency_key=idempotency_key,
        lock=True,
    )
    if existing is not None:
        return _resolve_existing(existing, digest)

    record = CommandIdempotencyRecord(
        actor_user_id=actor_user_id,
        operation=operation,
        idempotency_key=idempotency_key,
        request_digest=digest,
        state="processing",
    )
    try:
        with db.begin_nested():
            db.add(record)
            db.flush()
    except IntegrityError:
        existing = crud.find_idempotency(
            db,
            actor_user_id=actor_user_id,
            operation=operation,
            idempotency_key=idempotency_key,
            lock=True,
        )
        if existing is None:
            raise
        return _resolve_existing(existing, digest)
    return record, False


def _resolve_existing(
    record: CommandIdempotencyRecord, digest: bytes
) -> tuple[CommandIdempotencyRecord, bool]:
    if not hmac.compare_digest(record.request_digest, digest):
        raise AppException(
            "Idempotency key conflicts with another request",
            code="IDEMPOTENCY_CONFLICT",
            status_code=409,
        )
    if record.state == "completed":
        return record, True
    if record.state == "failed_retryable":
        record.state = "processing"
        record.resource_kind = None
        record.resource_id = None
        record.response_status = None
        record.response_body = None
        record.completed_at = None
        return record, False
    raise AppException(
        "Command is already processing", code="IDEMPOTENCY_IN_PROGRESS", status_code=409
    )


def complete(
    record: CommandIdempotencyRecord,
    *,
    resource_kind: str,
    resource_id: uuid.UUID,
    response_status: int,
    snapshot: IdempotencyResultSnapshot,
) -> None:
    allowed = _ALLOWED_SNAPSHOTS.get(record.operation)
    if allowed is None or type(snapshot) not in allowed:
        raise ValueError("Idempotency snapshot is not allowed for this operation")
    record.state = "completed"
    record.resource_kind = resource_kind
    record.resource_id = resource_id
    record.response_status = response_status
    record.response_body = snapshot.model_dump(mode="json")
    record.completed_at = datetime.now(UTC)
