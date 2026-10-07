import hmac
import uuid
from datetime import UTC, datetime

import jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException, NotFoundException
from app.core.rights_auth_provider import RightsAuthProvider, unavailable
from app.core.security import decode_verification_proof
from app.crud import identity_foundation as identity_crud
from app.crud import interview_participant as crud
from app.dependencies.participant_actor import ParticipantActor
from app.models.interview_participant import InterviewParticipant
from app.models.user import User
from app.schemas.interview_participant import ParticipantRead
from app.services import command_idempotency as idempotency
from app.services.collaboration_authorization import require_family_actor


def _snapshot(item: InterviewParticipant) -> idempotency.ParticipantResultSnapshot:
    return idempotency.ParticipantResultSnapshot.model_validate(item)


def _replay(record) -> ParticipantRead:
    try:
        return ParticipantRead.model_validate(record.response_body)
    except (TypeError, ValueError):
        raise AppException(
            "Idempotency result unavailable", code="IDEMPOTENCY_RESULT_UNAVAILABLE", status_code=409
        ) from None


def propose(
    db: Session,
    *,
    actor: User,
    interview_id: uuid.UUID,
    family_member_id: uuid.UUID | None,
    roles: str,
    idempotency_key: uuid.UUID,
):
    context = crud.get_interview_context(db, interview_id, lock=True)
    if context is None:
        raise NotFoundException("Interview not found")
    interview, member = context
    require_family_actor(db, actor=actor, family_id=member.family_id, lock=True)
    if family_member_id is not None and family_member_id != interview.family_member_id:
        raise AppException(
            "Participant subject mismatch", code="PARTICIPANT_CONFLICT", status_code=409
        )
    record, replay = idempotency.begin(
        db,
        actor_user_id=actor.id,
        operation="interview_participant.propose",
        idempotency_key=idempotency_key,
        digest=idempotency.safe_request_digest(
            idempotency.participant_propose_request(interview_id, family_member_id, roles)
        ),
    )
    if replay:
        return _replay(record)
    participant = InterviewParticipant(
        interview_id=interview.id,
        interview_scope_id=interview.id,
        family_member_id=family_member_id,
        roles="speaker",
        state="proposed",
        eligibility_state="unknown",
        version=1,
    )
    try:
        crud.add_and_flush(db, participant)
        idempotency.complete(
            record,
            resource_kind="interview_participant",
            resource_id=participant.id,
            response_status=201,
            snapshot=_snapshot(participant),
        )
        db.commit()
        db.refresh(participant)
        return participant
    except IntegrityError:
        db.rollback()
        raise AppException(
            "Participant conflict", code="PARTICIPANT_CONFLICT", status_code=409
        ) from None


def _invalid() -> AppException:
    return AppException(
        "Invalid participant verification", code="INVALID_VERIFICATION", status_code=401
    )


def _validate_proof(
    db: Session,
    *,
    actor: ParticipantActor,
    participant: InterviewParticipant,
    proof: str,
):
    try:
        payload = decode_verification_proof(proof)
        subject = uuid.UUID(payload["sub"])
        context_id = uuid.UUID(payload["context_id"])
        challenge_id = uuid.UUID(payload["challenge_id"])
        contact_id = uuid.UUID(payload["contact_id"])
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError, AttributeError):
        raise _invalid() from None
    contact = identity_crud.get_contact(db, contact_id)
    challenge = identity_crud.get_challenge(db, challenge_id)
    if (
        subject != actor.user.id
        or payload.get("principal_kind") != actor.user.principal_kind
        or payload.get("token_type") != "verification_proof"
        or payload.get("scope") != ["identity:verify"]
        or payload.get("context_kind") != "participant_confirmation"
        or context_id != participant.id
        or type(payload.get("auth_generation")) is not int
        or payload["auth_generation"] != actor.user.auth_generation
        or contact is None
        or contact.state != "verified"
        or contact.user_id != actor.user.id
        or challenge is None
        or challenge.state != "consumed"
        or challenge.user_id != actor.user.id
        or challenge.context_kind != "participant_confirmation"
        or challenge.context_id != participant.id
        or challenge.id != challenge_id
        or not hmac.compare_digest(challenge.channel_hash, contact.lookup_hash)
        or (actor.authentication == "rights" and actor.contact_id != contact.id)
    ):
        raise _invalid()
    return contact, challenge


def confirm(
    db: Session,
    *,
    actor: ParticipantActor,
    participant_id: uuid.UUID,
    proof: str,
    adult_autonomous_decision: bool,
    expected_version: int,
    idempotency_key: uuid.UUID,
    provider: RightsAuthProvider,
):
    if adult_autonomous_decision is not True:
        raise AppException(
            "Adult autonomous decision is required",
            code="PARTICIPANT_INELIGIBLE",
            status_code=422,
        )
    try:
        fingerprint = idempotency.verification_proof_fingerprint(provider, participant_id, proof)
    except Exception:  # noqa: BLE001 - provider boundary fails closed
        raise unavailable() from None
    record, replay = idempotency.begin(
        db,
        actor_user_id=actor.user.id,
        operation="interview_participant.confirm",
        idempotency_key=idempotency_key,
        digest=idempotency.safe_request_digest(
            idempotency.participant_confirm_request(
                participant_id, expected_version, fingerprint, adult_autonomous_decision
            )
        ),
    )
    if replay:
        return _replay(record)
    participant = crud.get_participant(db, participant_id, lock=True)
    if participant is None:
        db.rollback()
        raise NotFoundException("Participant not found")
    if participant.state != "proposed" or participant.version != expected_version:
        db.rollback()
        raise AppException(
            "Participant state conflict", code="PARTICIPANT_CONFLICT", status_code=409
        )
    current_user = identity_crud.locked_user(db, actor.user.id)
    if (
        current_user is None
        or current_user.principal_kind != actor.user.principal_kind
        or current_user.auth_generation != actor.user.auth_generation
        or (current_user.principal_kind == "account" and not current_user.is_active)
    ):
        db.rollback()
        raise _invalid()
    contact, challenge = _validate_proof(db, actor=actor, participant=participant, proof=proof)
    now = datetime.now(UTC)
    participant.user_id = actor.user.id
    participant.verified_contact_id = contact.id
    participant.verification_ref = challenge.id
    participant.verified_at = now
    participant.adult_declaration_at = now
    participant.eligibility_state = "eligible"
    participant.state = "verified"
    participant.version += 1
    try:
        db.flush()
        idempotency.complete(
            record,
            resource_kind="interview_participant",
            resource_id=participant.id,
            response_status=200,
            snapshot=_snapshot(participant),
        )
        db.commit()
        db.refresh(participant)
        return participant
    except IntegrityError:
        db.rollback()
        raise AppException(
            "Participant identity conflict", code="PARTICIPANT_CONFLICT", status_code=409
        ) from None


def inactivate(
    db: Session,
    *,
    actor: ParticipantActor,
    participant_id: uuid.UUID,
    expected_version: int,
    idempotency_key: uuid.UUID,
):
    record, replay = idempotency.begin(
        db,
        actor_user_id=actor.user.id,
        operation="interview_participant.inactivate",
        idempotency_key=idempotency_key,
        digest=idempotency.safe_request_digest(
            idempotency.participant_inactivate_request(participant_id, expected_version)
        ),
    )
    if replay:
        return _replay(record)
    participant = crud.get_participant(db, participant_id, lock=True)
    if participant is None or participant.user_id != actor.user.id:
        db.rollback()
        raise NotFoundException("Participant not found")
    if participant.state != "verified" or participant.version != expected_version:
        db.rollback()
        raise AppException(
            "Participant state conflict", code="PARTICIPANT_CONFLICT", status_code=409
        )
    participant.state = "inactive"
    participant.version += 1
    db.flush()
    idempotency.complete(
        record,
        resource_kind="interview_participant",
        resource_id=participant.id,
        response_status=200,
        snapshot=_snapshot(participant),
    )
    db.commit()
    db.refresh(participant)
    return participant


def get_self(db: Session, *, actor: ParticipantActor, participant_id: uuid.UUID):
    participant = crud.get_participant(db, participant_id)
    if participant is None or participant.user_id != actor.user.id:
        raise NotFoundException("Participant not found")
    return participant
