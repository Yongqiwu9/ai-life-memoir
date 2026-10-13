"""Offline Memory profile: one proposal authority, immutable revisions, current gates."""

import hmac
from datetime import UTC, datetime
from functools import wraps
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.exceptions import AppException, NotFoundException
from app.crud import memory as memory_crud
from app.crud import memory_workflow as crud
from app.models.memory import Memory
from app.models.memory_workflow import (
    ContentRevision,
    ExtractionBatch,
    MemoryCandidate,
    RevisionProposal,
)
from app.schemas.memory_workflow import RevisionPayload
from app.services import command_idempotency as commands
from app.services.memory_integrity import get_memory_integrity
from app.services.memory_policy import derive_required_purposes, get_memory_policy


def _error(code: str, status=409, *, details=None):
    return AppException(
        "Memory operation unavailable", code=code, status_code=status, details=details
    )


def _unknown_error(*, operation=None, idempotency_key=None, command_id=None):
    """Only registered operation names and already allocated UUIDs are echoed."""
    context = {"outcome": "unknown"}
    if operation in commands.MEMORY_OPERATIONS:
        context["operation"] = operation
    if isinstance(idempotency_key, UUID):
        context["idempotency_key"] = str(idempotency_key)
    if isinstance(command_id, UUID):
        context["command_id"] = str(command_id)
    return _error("COMMAND_OUTCOME_UNKNOWN", 503, details=context)


def _atomic(function):
    @wraps(function)
    def wrapped(db, *args, **kwargs):
        try:
            return function(db, *args, **kwargs)
        except AppException as exc:
            _rollback(db, unknown=exc if exc.code == "COMMAND_OUTCOME_UNKNOWN" else None)
            raise
        except Exception:  # noqa: BLE001 -- SQL/provider exception payloads must stay private.
            _rollback(db)
            raise _error("MEMORY_STORAGE_UNAVAILABLE", 503) from None

    return wrapped


def _rollback(db, *, unknown=None):
    try:
        db.rollback()
    except Exception:  # noqa: BLE001 -- unconfirmed rollback cannot be reported as completed.
        raise (unknown or _unknown_error()) from None


def commit(db: Session, record=None):
    # Capture before commit/rollback can expire ORM attributes or lose the connection.
    context = {}
    if record is not None:
        context = {
            "command_id": record.id,
            "operation": record.operation,
            "idempotency_key": record.idempotency_key,
        }
    try:
        db.commit()
    except Exception:  # noqa: BLE001 -- a driver failure cannot prove rollback or safe retry.
        # A driver exception cannot establish that the remote commit did not occur.
        failure = _unknown_error(**context)
        _rollback(db, unknown=failure)
        raise failure from None


def member_scope(db, user_id, member_id):
    member = crud.owned_member(db, user_id, member_id)
    if member is None:
        raise NotFoundException()
    return member


def owned(db, model, user_id, record_id, *, lock=False):
    record = crud.owned_record(db, model, user_id, record_id, lock=lock)
    if record is None:
        raise NotFoundException()
    member = member_scope(db, user_id, record.family_member_id)
    if record.family_scope_id != member.family_id:
        raise NotFoundException()
    return record


def owned_memory(db, user_id, memory_id, *, lock=False):
    memory = memory_crud.get_owned(db, user_id, memory_id, lock=lock)
    if memory is None:
        raise NotFoundException()
    return memory


def source(db, user_id, source_id, *, member_id=None, session_id=None, ai=False):
    reference = crud.source_reference(db, user_id, source_id)
    if reference is None:
        raise NotFoundException()
    if member_id is not None and reference.family_member_id != member_id:
        raise NotFoundException()
    if session_id is not None and reference.session_id != session_id:
        raise NotFoundException()
    allowed = ("text",) if ai else ("text", "audio_transcript")
    if reference.role != "user" or reference.source not in allowed:
        raise _error("INVALID_SOURCE", 422)
    return reference


def gate(db, user_id, reference, *, operation, purposes, policy=None, previous_stamp=None):
    return (policy or get_memory_policy()).require(
        operation=operation,
        user_id=user_id,
        family_scope_id=reference.family_id,
        family_member_id=reference.family_member_id,
        source_scope_id=reference.id,
        required_purposes=tuple(purposes),
        previous_stamp=previous_stamp,
    )


def revision_gate(db, user_id, revision, *, operation="read", policy=None, previous_stamp=None):
    reference = source(db, user_id, revision.source_message_id, member_id=revision.family_member_id)
    if revision.source_scope_id != reference.id or revision.family_scope_id != reference.family_id:
        raise NotFoundException()
    if revision.body_state != "present":
        raise _error("CONTENT_RESTRICTED", 403)
    previous = previous_stamp
    if previous is None:
        previous = crud.revision_receipt(db, revision.id)
    return gate(
        db,
        user_id,
        reference,
        operation=operation,
        purposes=revision.required_purposes,
        policy=policy,
        previous_stamp=previous,
    )


def verify_revision(db, revision, *, integrity=None):
    integrity = integrity or get_memory_integrity()
    integrity.require_available(key_id=revision.digest_key_id)
    row = crud.revision_body(db, revision.id)
    if row is None or row.body_state != "present" or row.payload is None:
        raise _error("CONTENT_RESTRICTED", 403)
    payload = RevisionPayload.model_validate(row.payload)
    integrity.verify_content(
        payload,
        source_scope_id=row.source_scope_id,
        family_member_id=row.family_member_id,
        derivation_profile=row.derivation_profile,
        required_purposes=row.required_purposes,
        digest=row.content_digest,
        scheme=row.digest_scheme,
        key_id=row.digest_key_id,
    )
    return row, payload


def revision_metadata(revision):
    return {
        "id": revision.id,
        "candidate_id": revision.candidate_id,
        "memory_id": revision.memory_id,
        "ordinal": revision.ordinal,
        "parent_revision_id": revision.parent_revision_id,
        "origin_revision_id": revision.origin_revision_id,
        "body_state": revision.body_state,
        "author_mode": revision.author_mode,
        "created_at": revision.created_at,
        "updated_at": revision.updated_at,
        "source_message_id": revision.source_message_id,
    }


def candidate_metadata(candidate):
    return {
        "id": candidate.id,
        "family_member_id": candidate.family_member_id,
        "source_message_id": candidate.source_message_id,
        "origin": candidate.origin,
        "batch_id": candidate.batch_id,
        "batch_ordinal": candidate.batch_ordinal,
        "version": candidate.version,
        "revision_counter": candidate.revision_counter,
        "promoted_memory_id": candidate.promoted_memory_id,
        "created_at": candidate.created_at,
        "updated_at": candidate.updated_at,
    }


def proposal_metadata(proposal):
    return {
        "id": proposal.id,
        "candidate_id": proposal.candidate_id,
        "memory_id": proposal.memory_id,
        "input_revision_id": proposal.input_revision_id,
        "state": proposal.state,
        "decision_code": proposal.decision_code,
        "version": proposal.version,
        "base_version": proposal.base_version,
        "base_revision_id": proposal.base_revision_id,
        "result_memory_id": proposal.result_memory_id,
        "result_memory_revision_id": proposal.result_memory_revision_id,
        "submitted_at": proposal.submitted_at,
        "decided_at": proposal.decided_at,
        "created_at": proposal.created_at,
        "updated_at": proposal.updated_at,
    }


def _check_version(value, expected):
    if value != expected:
        raise _error("VERSION_CONFLICT")


def _command(db, user_id, operation, key, *, scope, versions, payload=None, integrity=None):
    return commands.begin_memory(
        db,
        actor_user_id=user_id,
        operation=operation,
        idempotency_key=key,
        target_scope=scope,
        expected_versions=versions,
        payload=payload,
        integrity=integrity,
    )


def new_revision(
    db,
    user_id,
    target,
    payload,
    stamp,
    *,
    parent_id=None,
    derivation_profile,
    required_purposes,
    author_mode="manual",
    integrity=None,
):
    candidate = isinstance(target, MemoryCandidate)
    target.revision_counter += 1
    db.flush()
    fingerprint = (integrity or get_memory_integrity()).content_digest(
        payload,
        source_scope_id=target.source_message_id,
        family_member_id=target.family_member_id,
        derivation_profile=derivation_profile,
        required_purposes=required_purposes,
    )
    member = member_scope(db, user_id, target.family_member_id)
    revision = ContentRevision(
        id=uuid4(),
        candidate_id=target.id if candidate else None,
        memory_id=None if candidate else target.id,
        family_member_id=target.family_member_id,
        family_scope_id=member.family_id,
        source_message_id=target.source_message_id,
        source_scope_id=target.source_message_id,
        ordinal=target.revision_counter,
        parent_revision_id=parent_id,
        origin_revision_id=None,
        author_mode=author_mode,
        actor_user_id=user_id,
        derivation_profile=derivation_profile,
        required_purposes=list(required_purposes),
        input_permission_stamp=stamp.receipt(),
        payload=payload.model_dump(mode="json"),
        body_state="present",
        content_digest=fingerprint.digest,
        digest_scheme=fingerprint.scheme,
        digest_key_id=fingerprint.key_id,
    )
    crud.add_flush(db, revision)
    proposal = RevisionProposal(
        id=uuid4(),
        profile="offline_memory.v1",
        family_member_id=target.family_member_id,
        family_scope_id=member.family_id,
        candidate_id=target.id if candidate else None,
        memory_id=None if candidate else target.id,
        input_revision_id=revision.id,
        proposed_by_user_id=user_id,
        base_version=target.version,
        base_revision_id=None if candidate else target.current_revision_id,
        payload_digest=fingerprint.digest,
        digest_scheme=fingerprint.scheme,
        digest_key_id=fingerprint.key_id,
        state="draft",
        version=0,
    )
    crud.add_flush(db, proposal)
    return revision, proposal


@_atomic
def manual_candidate(db, user_id, member_id, data, idempotency_key, *, policy=None, integrity=None):
    member = member_scope(db, user_id, member_id)
    reference = source(db, user_id, data.source_message_id, member_id=member_id)
    integrity = integrity or get_memory_integrity()
    record, replay = _command(
        db,
        user_id,
        "memory.candidate.manual",
        idempotency_key,
        scope={"member_id": str(member_id), "source_id": str(reference.id)},
        versions={},
        payload=data.model_dump(mode="json"),
        integrity=integrity,
    )
    if replay:
        return commands.replay_memory(record)
    purposes = derive_required_purposes(reference.source)
    stamp = gate(
        db, user_id, reference, operation="manual_revision", purposes=purposes, policy=policy
    )
    candidate = MemoryCandidate(
        id=uuid4(),
        family_member_id=member_id,
        family_scope_id=member.family_id,
        source_message_id=reference.id,
        source_scope_id=reference.id,
        origin="manual",
        created_by_user_id=user_id,
        version=0,
        revision_counter=0,
    )
    crud.add_flush(db, candidate)
    revision, proposal = new_revision(
        db,
        user_id,
        candidate,
        data.payload,
        stamp,
        required_purposes=purposes,
        derivation_profile="transcript_derived"
        if reference.source == "audio_transcript"
        else "raw_manual",
        integrity=integrity,
    )
    snapshot = {
        "candidate_id": candidate.id,
        "revision_id": revision.id,
        "proposal_id": proposal.id,
        "version": candidate.version,
        "proposal_version": 0,
    }
    commands.complete_memory(
        record,
        resource_kind="candidate",
        resource_id=candidate.id,
        response_status=201,
        snapshot=snapshot,
    )
    commit(db, record)
    return snapshot, 201


@_atomic
def _create_revision(db, user_id, target_id, data, key, *, candidate, policy=None, integrity=None):
    target = (
        owned(db, MemoryCandidate, user_id, target_id)
        if candidate
        else owned_memory(db, user_id, target_id)
    )
    integrity = integrity or get_memory_integrity()
    record, replay = _command(
        db,
        user_id,
        "memory.candidate.revise" if candidate else "memory.revise",
        key,
        scope={"target_id": str(target_id), "member_id": str(target.family_member_id)},
        versions={"expected_version": data.expected_version},
        payload=data.model_dump(mode="json"),
        integrity=integrity,
    )
    if replay:
        return commands.replay_memory(record)
    target = (
        owned(db, MemoryCandidate, user_id, target_id, lock=True)
        if candidate
        else owned_memory(db, user_id, target_id, lock=True)
    )
    _check_version(target.version, data.expected_version)
    if candidate and target.promoted_memory_id is not None:
        raise _error("CANDIDATE_ALREADY_PROMOTED")
    parent = None
    if data.parent_revision_id is not None:
        parent = owned(db, ContentRevision, user_id, data.parent_revision_id)
        if (parent.candidate_id if candidate else parent.memory_id) != target.id:
            raise NotFoundException()
    if candidate and parent is None:
        raise _error("INVALID_SOURCE", 422)
    if not candidate and target.current_revision_id != data.parent_revision_id:
        raise _error("VERSION_CONFLICT")
    if parent is not None:
        stamp = revision_gate(db, user_id, parent, operation="manual_revision", policy=policy)
        purposes, profile = tuple(parent.required_purposes), parent.derivation_profile
    else:
        reference = source(db, user_id, target.source_message_id, member_id=target.family_member_id)
        purposes = derive_required_purposes(reference.source)
        profile = "transcript_derived" if reference.source == "audio_transcript" else "raw_manual"
        stamp = gate(
            db, user_id, reference, operation="manual_revision", purposes=purposes, policy=policy
        )
    revision, proposal = new_revision(
        db,
        user_id,
        target,
        data.payload,
        stamp,
        parent_id=data.parent_revision_id,
        derivation_profile=profile,
        required_purposes=purposes,
        integrity=integrity,
    )
    snapshot = {
        "revision_id": revision.id,
        "proposal_id": proposal.id,
        "version": target.version,
        "proposal_version": 0,
        "candidate_id" if candidate else "memory_id": target.id,
    }
    commands.complete_memory(
        record,
        resource_kind="candidate" if candidate else "memory",
        resource_id=target.id,
        response_status=201,
        snapshot=snapshot,
    )
    commit(db, record)
    return snapshot, 201


def create_candidate_revision(db, user_id, candidate_id, data, idempotency_key, **kwargs):
    return _create_revision(
        db, user_id, candidate_id, data, idempotency_key, candidate=True, **kwargs
    )


def create_memory_revision(db, user_id, memory_id, data, idempotency_key, **kwargs):
    return _create_revision(
        db, user_id, memory_id, data, idempotency_key, candidate=False, **kwargs
    )


def _proposal_command(db, user_id, proposal_id, data, key, operation):
    proposal = owned(db, RevisionProposal, user_id, proposal_id)
    versions = {"expected_version": data.expected_version}
    if hasattr(data, "expected_target_version"):
        versions["expected_target_version"] = data.expected_target_version
    if hasattr(data, "decision_code"):
        versions["decision_code"] = data.decision_code
    record, replay = _command(
        db,
        user_id,
        operation,
        key,
        scope={"proposal_id": str(proposal_id), "member_id": str(proposal.family_member_id)},
        versions=versions,
    )
    return proposal, record, replay


def _locked_target(db, user_id, proposal):
    if proposal.candidate_id is not None:
        return owned(db, MemoryCandidate, user_id, proposal.candidate_id, lock=True)
    return owned_memory(db, user_id, proposal.memory_id, lock=True)


def _base_valid(target, proposal):
    if target.version != proposal.base_version:
        return False
    if isinstance(target, MemoryCandidate):
        return target.promoted_memory_id is None and proposal.base_revision_id is None
    return target.current_revision_id == proposal.base_revision_id


def _verified_input(db, user_id, proposal, *, operation, policy=None, integrity=None):
    revision = owned(db, ContentRevision, user_id, proposal.input_revision_id)
    if (
        revision.candidate_id != proposal.candidate_id
        or revision.memory_id != proposal.memory_id
        or revision.family_member_id != proposal.family_member_id
    ):
        raise _error("INVALID_APPROVED_REVISION", 422)
    stamp = revision_gate(db, user_id, revision, operation=operation, policy=policy)
    revision, payload = verify_revision(db, revision, integrity=integrity)
    proof = crud.proposal_proof(db, proposal.id)
    if (
        proof.digest_scheme != revision.digest_scheme
        or proof.digest_key_id != revision.digest_key_id
        or not hmac.compare_digest(proof.payload_digest, revision.content_digest)
    ):
        raise _error("MEMORY_INTEGRITY_UNAVAILABLE", 503)
    return revision, payload, stamp


@_atomic
def submit(db, user_id, proposal_id, data, idempotency_key, *, policy=None, integrity=None):
    proposal, record, replay = _proposal_command(
        db, user_id, proposal_id, data, idempotency_key, "memory.proposal.submit"
    )
    if replay:
        return commands.replay_memory(record)
    target = _locked_target(db, user_id, proposal)
    proposal = owned(db, RevisionProposal, user_id, proposal_id, lock=True)
    _check_version(proposal.version, data.expected_version)
    _check_version(target.version, data.expected_target_version)
    if proposal.state != "draft":
        raise _error("PROPOSAL_STATE_CONFLICT")
    if not _base_valid(target, proposal):
        raise _error("PROPOSAL_STALE")
    _verified_input(db, user_id, proposal, operation="submit", policy=policy, integrity=integrity)
    proposal.state, proposal.submitted_at = "submitted", datetime.now(UTC)
    proposal.version += 1
    snapshot = {
        "proposal_id": proposal.id,
        "state": proposal.state,
        "version": proposal.version,
        "target_version": target.version,
    }
    commands.complete_memory(
        record,
        resource_kind="proposal",
        resource_id=proposal.id,
        response_status=200,
        snapshot=snapshot,
    )
    commit(db, record)
    return snapshot, 200


@_atomic
def approve(db, user_id, proposal_id, data, idempotency_key, *, policy=None, integrity=None):
    proposal, record, replay = _proposal_command(
        db, user_id, proposal_id, data, idempotency_key, "memory.proposal.approve"
    )
    if replay:
        return commands.replay_memory(record)
    target = _locked_target(db, user_id, proposal)
    proposal = owned(db, RevisionProposal, user_id, proposal_id, lock=True)
    _check_version(proposal.version, data.expected_version)
    if proposal.state != "submitted":
        raise _error("PROPOSAL_STATE_CONFLICT")
    if not _base_valid(target, proposal):
        proposal.state, proposal.decided_at = "stale", datetime.now(UTC)
        proposal.version += 1
        snapshot = {"proposal_id": proposal.id, "state": "stale", "version": proposal.version}
        commands.complete_memory(
            record,
            resource_kind="proposal",
            resource_id=proposal.id,
            response_status=409,
            snapshot=snapshot,
        )
        commit(db, record)
        raise _error("PROPOSAL_STALE")
    _check_version(target.version, data.expected_target_version)
    revision, payload, stamp = _verified_input(
        db, user_id, proposal, operation="approve", policy=policy, integrity=integrity
    )
    if isinstance(target, MemoryCandidate):
        memory = Memory(
            id=uuid4(),
            family_member_id=target.family_member_id,
            source_message_id=target.source_message_id,
            record_origin="versioned",
            version=0,
            revision_counter=1,
            origin_candidate_id=target.id,
            title=None,
            content=None,
            time_text=None,
            place=None,
            emotion=None,
        )
        crud.add_flush(db, memory)
        output = ContentRevision(
            id=uuid4(),
            candidate_id=None,
            memory_id=memory.id,
            family_member_id=revision.family_member_id,
            family_scope_id=revision.family_scope_id,
            source_message_id=revision.source_message_id,
            source_scope_id=revision.source_scope_id,
            ordinal=1,
            parent_revision_id=None,
            origin_revision_id=revision.id,
            actor_user_id=user_id,
            author_mode="promotion",
            derivation_profile=revision.derivation_profile,
            required_purposes=list(revision.required_purposes),
            input_permission_stamp=stamp.receipt(),
            body_state="present",
            payload=payload.model_dump(mode="json"),
            content_digest=revision.content_digest,
            digest_scheme=revision.digest_scheme,
            digest_key_id=revision.digest_key_id,
        )
        crud.add_flush(db, output)
        # Every value is copied, never regenerated or combined during approval.
        if (
            output.payload != revision.payload
            or output.required_purposes != revision.required_purposes
        ):
            raise _error("MEMORY_INTEGRITY_UNAVAILABLE", 503)
    else:
        memory, output = target, revision
    proposal.state = "approved"
    proposal.version += 1
    proposal.decided_at, proposal.decided_by_user_id = datetime.now(UTC), user_id
    proposal.result_memory_id, proposal.result_memory_revision_id = memory.id, output.id
    proposal.approval_permission_stamp = stamp.receipt()
    db.flush()
    memory.current_revision_id, memory.current_approval_proposal_id = output.id, proposal.id
    memory.version += 1
    if isinstance(target, MemoryCandidate):
        target.promoted_memory_id = memory.id
        target.version += 1
    snapshot = {
        "proposal_id": proposal.id,
        "state": "approved",
        "version": proposal.version,
        "memory_id": memory.id,
        "memory_revision_id": output.id,
        "target_version": target.version,
    }
    commands.complete_memory(
        record,
        resource_kind="proposal",
        resource_id=proposal.id,
        response_status=200,
        snapshot=snapshot,
    )
    commit(db, record)
    return snapshot, 200


@_atomic
def _stop_proposal(db, user_id, proposal_id, data, key, *, rejecting):
    proposal, record, replay = _proposal_command(
        db,
        user_id,
        proposal_id,
        data,
        key,
        "memory.proposal.reject" if rejecting else "memory.proposal.withdraw",
    )
    if replay:
        return commands.replay_memory(record)
    _locked_target(db, user_id, proposal)
    proposal = owned(db, RevisionProposal, user_id, proposal_id, lock=True)
    _check_version(proposal.version, data.expected_version)
    allowed = ("submitted",) if rejecting else ("draft", "submitted")
    if proposal.state not in allowed:
        raise _error("PROPOSAL_STATE_CONFLICT")
    proposal.state = "rejected" if rejecting else "withdrawn"
    proposal.version += 1
    proposal.decided_at, proposal.decided_by_user_id = datetime.now(UTC), user_id
    if rejecting:
        proposal.decision_code = data.decision_code
    snapshot = {"proposal_id": proposal.id, "state": proposal.state, "version": proposal.version}
    commands.complete_memory(
        record,
        resource_kind="proposal",
        resource_id=proposal.id,
        response_status=200,
        snapshot=snapshot,
    )
    commit(db, record)
    return snapshot, 200


def reject(db, user_id, proposal_id, data, idempotency_key):
    return _stop_proposal(db, user_id, proposal_id, data, idempotency_key, rejecting=True)


def withdraw(db, user_id, proposal_id, data, idempotency_key):
    return _stop_proposal(db, user_id, proposal_id, data, idempotency_key, rejecting=False)


def get_candidate(db, user_id, candidate_id):
    candidate = owned(db, MemoryCandidate, user_id, candidate_id)
    result = candidate_metadata(candidate)
    pairs = crud.revision_proposal_ids(db, candidate_id)
    result["revision_ids"] = [pair[0] for pair in pairs]
    result["proposal_ids"] = [pair[1] for pair in pairs]
    return result


def list_candidates(db, user_id, member_id, page=1, page_size=20):
    member_scope(db, user_id, member_id)
    records, total = crud.list_records(
        db, MemoryCandidate, MemoryCandidate.family_member_id == member_id, page, page_size
    )
    return [candidate_metadata(row) for row in records], total


def list_revisions(db, user_id, target_id, page=1, page_size=20, *, candidate=True):
    if candidate:
        owned(db, MemoryCandidate, user_id, target_id)
        condition = ContentRevision.candidate_id == target_id
    else:
        owned_memory(db, user_id, target_id)
        condition = ContentRevision.memory_id == target_id
    rows, total = crud.list_records(db, ContentRevision, condition, page, page_size)
    return [revision_metadata(row) for row in rows], total


def get_proposal(db, user_id, proposal_id):
    return proposal_metadata(owned(db, RevisionProposal, user_id, proposal_id))


def get_revision_content(db, user_id, revision_id, *, policy=None, integrity=None):
    revision = owned(db, ContentRevision, user_id, revision_id)
    revision_gate(db, user_id, revision, policy=policy)
    revision, payload = verify_revision(db, revision, integrity=integrity)
    return {
        "revision_id": revision.id,
        "source_message_id": revision.source_message_id,
        "payload": payload.model_dump(mode="json"),
    }


def approved_content(
    db, user_id, memory, revision_id, proposal_id, *, operation="read", policy=None, integrity=None
):
    revision = owned(db, ContentRevision, user_id, revision_id)
    proposal = owned(db, RevisionProposal, user_id, proposal_id)
    if (
        revision.memory_id != memory.id
        or revision.family_member_id != memory.family_member_id
        or proposal.state != "approved"
        or proposal.result_memory_id != memory.id
        or proposal.result_memory_revision_id != revision.id
    ):
        raise _error("INVALID_APPROVED_REVISION", 422)
    proof = crud.proposal_proof(db, proposal.id)
    revision_gate(
        db,
        user_id,
        revision,
        operation=operation,
        policy=policy,
        previous_stamp=proof.approval_permission_stamp,
    )
    revision, payload = verify_revision(db, revision, integrity=integrity)
    if (
        proof.payload_digest is None
        or proof.digest_scheme != revision.digest_scheme
        or proof.digest_key_id != revision.digest_key_id
        or not hmac.compare_digest(proof.payload_digest, revision.content_digest)
    ):
        raise _error("MEMORY_INTEGRITY_UNAVAILABLE", 503)
    return revision, payload


def _command_status(db, user_id, member_id, operation, idempotency_key):
    """Read only: a missing record is unknown, never proof of rollback."""
    record = crud.find_command(db, user_id, operation, idempotency_key)
    if record is None or record.resource_id is None:
        raise _unknown_error(operation=operation, idempotency_key=idempotency_key)
    if record.resource_kind in ("batch", "candidate", "proposal"):
        model = {
            "batch": ExtractionBatch,
            "candidate": MemoryCandidate,
            "proposal": RevisionProposal,
        }[record.resource_kind]
        resource = crud.owned_record(db, model, user_id, record.resource_id)
    elif record.resource_kind == "memory":
        resource = memory_crud.get_owned(db, user_id, record.resource_id)
    elif record.resource_kind == "memoir":
        from app.crud import memoir as memoir_crud

        resource = memoir_crud.get_owned(db, user_id, record.resource_id)
    else:
        resource = None
    if resource is None:
        # A record of this actor still does not prove it belongs to this URL member.
        raise _unknown_error(operation=operation, idempotency_key=idempotency_key)
    if resource.family_member_id != member_id:
        raise NotFoundException()
    if record.state == "processing":
        return {
            "command_id": record.id,
            "resource_kind": record.resource_kind,
            "resource_id": record.resource_id,
            "state": getattr(resource, "state", "processing"),
            "version": getattr(resource, "version", 0),
        }, 202
    safe_command_id = record.id
    try:
        result, status = commands.replay_memory(record)
    except Exception:  # noqa: BLE001 -- malformed persisted metadata is an unknown outcome.
        raise _unknown_error(
            operation=operation, idempotency_key=idempotency_key, command_id=safe_command_id
        ) from None
    result = dict(result)
    result["command_id"] = record.id
    # Reconciliation reports the persisted terminal result, not a new command failure.
    return result, 202 if status == 202 else 200


def command_status(db, user_id, member_id, operation, idempotency_key):
    with db.no_autoflush:
        try:
            member_scope(db, user_id, member_id)
        except AppException:
            raise
        except Exception:  # noqa: BLE001 -- storage unavailable before scope is established.
            raise _unknown_error() from None
        if operation not in commands.MEMORY_OPERATIONS:
            raise _error("INVALID_MEMORY_REQUEST", 422)
        try:
            return _command_status(db, user_id, member_id, operation, idempotency_key)
        except AppException:
            raise
        except Exception:  # noqa: BLE001 -- only authorized request identifiers may be echoed.
            # Reconciliation never repairs, begins or commits a command in response
            # to a storage error. The caller owns Session cleanup.
            raise _unknown_error(operation=operation, idempotency_key=idempotency_key) from None
