"""Prepare / lock-free offline Provider / fresh-gated atomic publication."""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError

from app.core.exceptions import AppException, NotFoundException
from app.crud import memory_workflow as crud
from app.models.memory_workflow import ExtractionBatch, MemoryCandidate
from app.schemas.memory_workflow import MemoryExtractionRequest, MemoryExtractionResult
from app.services import command_idempotency as commands
from app.services import memory_review as review
from app.services.ai_memory_client import get_memory_client, require_offline_provider
from app.services.memory_integrity import get_memory_integrity
from app.services.memory_policy import derive_required_purposes


def metadata(db, batch):
    return {
        "id": batch.id,
        "session_id": batch.session_id,
        "family_member_id": batch.family_member_id,
        "source_message_id": batch.source_message_id,
        "state": batch.state,
        "version": batch.version,
        "candidate_count": batch.candidate_count,
        "failure_code": batch.failure_code,
        "discard_reason": batch.discard_reason,
        "created_at": batch.created_at,
        "updated_at": batch.updated_at,
        "finished_at": batch.finished_at,
        "candidate_ids": crud.candidate_references(db, batch.id),
    }


def _snapshot(db, batch):
    return {
        "batch_id": batch.id,
        "state": batch.state,
        "version": batch.version,
        "candidate_count": batch.candidate_count,
        "failure_code": batch.failure_code,
        "discard_reason": batch.discard_reason,
        "candidate_ids": crud.candidate_references(db, batch.id),
    }


def _terminal(
    db, batch, record, *, state, failure_code=None, discard_reason=None, count=None, status=200
):
    batch.state = state
    batch.version += 1
    batch.failure_code, batch.discard_reason = failure_code, discard_reason
    batch.candidate_count, batch.finished_at = count, datetime.now(UTC)
    db.flush()
    snapshot = _snapshot(db, batch)
    commands.complete_memory(
        record,
        resource_kind="batch",
        resource_id=batch.id,
        response_status=status,
        snapshot=snapshot,
    )
    review.commit(db, record)
    return snapshot, status


@review._atomic
def _prepare(db, user_id, session_id, data, key, *, policy=None, integrity=None, client=None):
    session = crud.owned_session(db, user_id, session_id)
    if session is None:
        raise NotFoundException()
    reference = review.source(db, user_id, data.source_message_id, session_id=session_id, ai=True)
    record, replay = review._command(
        db,
        user_id,
        "memory.extract",
        key,
        scope={
            "session_id": str(session_id),
            "source_id": str(reference.id),
            "member_id": str(reference.family_member_id),
        },
        versions={},
    )
    if replay:
        result = commands.replay_memory(record)
        if result[1] == 202 and record.resource_id is not None:
            pending = review.owned(db, ExtractionBatch, user_id, record.resource_id)
            result = (
                {
                    "command_id": record.id,
                    "batch_id": pending.id,
                    "state": pending.state,
                    "version": pending.version,
                },
                202,
            )
        # No Provider call or body query on any replay, including pending/failed.
        db.rollback()
        return None, None, result
    (integrity or get_memory_integrity()).require_available()
    purposes = derive_required_purposes(reference.source, ai_analysis=True)
    stamp = review.gate(
        db, user_id, reference, operation="extract", purposes=purposes, policy=policy
    )
    # Resolve only new, Owner-gated requests. Replays never require a live adapter.
    provider = client if client is not None else get_memory_client()
    provider_id = require_offline_provider(provider)
    content = crud.source_content(db, reference.id)
    if content is None:
        raise review._error("CONTENT_RESTRICTED", 403)
    if len(content) > 10000:
        raise review._error("SOURCE_TOO_LARGE", 422)
    batch_id = uuid4()
    try:
        request = MemoryExtractionRequest(
            request_id=batch_id, source_message_id=reference.id, source_text=content
        )
    except ValidationError:
        raise review._error("INVALID_SOURCE", 422) from None
    batch = ExtractionBatch(
        id=batch_id,
        requested_by_user_id=user_id,
        session_id=session_id,
        family_member_id=reference.family_member_id,
        family_scope_id=reference.family_id,
        source_message_id=reference.id,
        source_scope_id=reference.id,
        contract_version=request.contract_version,
        policy_version=stamp.policy_version,
        permission_stamp=stamp.receipt(),
        provider_id=provider_id,
        request_fingerprint=record.request_digest,
        idempotency_key=key,
        state="pending",
        version=0,
    )
    crud.add_flush(db, batch)
    record.resource_kind, record.resource_id = "batch", batch_id
    db.flush()
    review.commit(db, record)
    # DTO and scalars are detached from ORM access before the call phase.
    return request, provider, None


@review._atomic
def _finish_failure(db, user_id, batch_id, key, code, status):
    record = crud.find_command(db, user_id, "memory.extract", key, lock=True)
    batch = review.owned(db, ExtractionBatch, user_id, batch_id, lock=True)
    if record is None:
        raise review._error("COMMAND_OUTCOME_UNKNOWN", 503)
    if batch.state != "pending":
        return _snapshot(db, batch), 200
    return _terminal(db, batch, record, state="failed", failure_code=code, status=status)


@review._atomic
def _finalize(db, user_id, request, key, result, *, policy=None, integrity=None):
    record = crud.find_command(db, user_id, "memory.extract", key, lock=True)
    batch = review.owned(db, ExtractionBatch, user_id, request.request_id, lock=True)
    if record is None:
        raise review._error("COMMAND_OUTCOME_UNKNOWN", 503)
    if batch.state != "pending":
        # A cancelled/finished batch is never reopened by a late call result.
        return _snapshot(db, batch), 200
    try:
        reference = review.source(
            db,
            user_id,
            request.source_message_id,
            member_id=batch.family_member_id,
            session_id=batch.session_id,
            ai=True,
        )
        purposes = derive_required_purposes(reference.source, ai_analysis=True)
        stamp = review.gate(
            db,
            user_id,
            reference,
            operation="extract",
            purposes=purposes,
            policy=policy,
            previous_stamp=crud.batch_receipt(db, batch.id),
        )
    except AppException as exc:
        if exc.code not in {"CONTENT_RESTRICTED", "NOT_FOUND", "INVALID_SOURCE"}:
            raise
        return _terminal(
            db,
            batch,
            record,
            state="discarded",
            discard_reason="source_or_permission_changed",
            status=409,
        )
    (integrity or get_memory_integrity()).require_available()
    if crud.source_content(db, reference.id) != request.source_text:
        return _terminal(
            db, batch, record, state="discarded", discard_reason="source_changed", status=409
        )
    validated = MemoryExtractionResult.model_validate(result).validate_binding(request)
    for ordinal, payload in enumerate(validated.candidates, start=1):
        candidate = MemoryCandidate(
            id=uuid4(),
            family_member_id=batch.family_member_id,
            family_scope_id=batch.family_scope_id,
            source_message_id=batch.source_message_id,
            source_scope_id=batch.source_scope_id,
            origin="extraction",
            batch_id=batch.id,
            batch_ordinal=ordinal,
            created_by_user_id=user_id,
            version=0,
            revision_counter=0,
        )
        crud.add_flush(db, candidate)
        review.new_revision(
            db,
            user_id,
            candidate,
            payload,
            stamp,
            derivation_profile="ai_derived",
            required_purposes=purposes,
            author_mode="mock_ai",
            integrity=integrity,
        )
    return _terminal(
        db, batch, record, state="completed", count=len(validated.candidates), status=201
    )


def start(
    db, user_id, session_id, data, idempotency_key, *, policy=None, integrity=None, client=None
):
    integrity = integrity or get_memory_integrity()
    # Ensure content integrity capability is available before source body processing.
    # _prepare's source gate also defaults unavailable; no production shortcut exists.
    request, provider, replay = _prepare(
        db,
        user_id,
        session_id,
        data,
        idempotency_key,
        policy=policy,
        integrity=integrity,
        client=client,
    )
    if replay is not None:
        return replay
    batch_id = request.request_id
    try:
        if db.in_transaction():
            raise RuntimeError("Provider call requires no database transaction")
        # Recheck the same object before invocation; never substitute an adapter.
        require_offline_provider(provider)
        result = provider.extract(request)
        result = MemoryExtractionResult.model_validate(result).validate_binding(request)
    except TimeoutError:
        terminal = _finish_failure(
            db, user_id, batch_id, idempotency_key, "AI_PROVIDER_TIMEOUT", 503
        )
        if terminal[1] == 200:
            return terminal
        raise review._error("AI_PROVIDER_TIMEOUT", 503) from None
    except (ValidationError, ValueError, TypeError):
        terminal = _finish_failure(
            db, user_id, batch_id, idempotency_key, "AI_INVALID_RESPONSE", 502
        )
        if terminal[1] == 200:
            return terminal
        raise review._error("AI_INVALID_RESPONSE", 502) from None
    except AppException as exc:
        code = (
            exc.code
            if exc.code
            in {
                "AI_UNAVAILABLE",
                "AI_INVALID_RESPONSE",
                "AI_PROVIDER_TIMEOUT",
                "MEMORY_PROCESSING_UNAVAILABLE",
            }
            else "AI_UNAVAILABLE"
        )
        terminal = _finish_failure(db, user_id, batch_id, idempotency_key, code, 503)
        if terminal[1] == 200:
            return terminal
        raise review._error(code, 503) from None
    except Exception:  # noqa: BLE001 -- provider failures may contain private source material.
        terminal = _finish_failure(db, user_id, batch_id, idempotency_key, "AI_UNAVAILABLE", 503)
        if terminal[1] == 200:
            return terminal
        raise review._error("AI_UNAVAILABLE", 503) from None
    try:
        return _finalize(
            db, user_id, request, idempotency_key, result, policy=policy, integrity=integrity
        )
    except AppException as exc:
        if exc.code == "COMMAND_OUTCOME_UNKNOWN":
            # Never overwrite a possibly committed successful result after an uncertain commit.
            raise
        if exc.code in {"MEMORY_PROCESSING_UNAVAILABLE", "MEMORY_INTEGRITY_UNAVAILABLE"}:
            raise
        _finish_failure(db, user_id, batch_id, idempotency_key, "PERSISTENCE_FAILED", 503)
        raise review._error("MEMORY_STORAGE_UNAVAILABLE", 503) from None


def get_batch(db, user_id, batch_id):
    return metadata(db, review.owned(db, ExtractionBatch, user_id, batch_id))


def list_batches(db, user_id, session_id, page=1, page_size=20):
    if crud.owned_session(db, user_id, session_id) is None:
        raise NotFoundException()
    rows, total = crud.list_records(
        db, ExtractionBatch, ExtractionBatch.session_id == session_id, page, page_size
    )
    return [metadata(db, batch) for batch in rows], total


@review._atomic
def cancel_batch(db, user_id, batch_id, data, idempotency_key):
    batch = review.owned(db, ExtractionBatch, user_id, batch_id)
    record, replay = review._command(
        db,
        user_id,
        "memory.extraction.cancel",
        idempotency_key,
        scope={"batch_id": str(batch_id), "member_id": str(batch.family_member_id)},
        versions={"expected_version": data.expected_version},
    )
    if replay:
        return commands.replay_memory(record)
    extraction_record = crud.find_command(
        db, batch.requested_by_user_id, "memory.extract", batch.idempotency_key, lock=True
    )
    if extraction_record is None:
        raise review._error("COMMAND_OUTCOME_UNKNOWN", 503)
    batch = review.owned(db, ExtractionBatch, user_id, batch_id, lock=True)
    review._check_version(batch.version, data.expected_version)
    if batch.state != "pending":
        raise review._error("BATCH_STATE_CONFLICT")
    batch.state, batch.discard_reason = "cancelled", "cancelled_by_owner"
    batch.version += 1
    batch.finished_at = datetime.now(UTC)
    db.flush()
    snapshot = _snapshot(db, batch)
    commands.complete_memory(
        extraction_record,
        resource_kind="batch",
        resource_id=batch.id,
        response_status=200,
        snapshot=snapshot,
    )
    commands.complete_memory(
        record, resource_kind="batch", resource_id=batch.id, response_status=200, snapshot=snapshot
    )
    review.commit(db, record)
    return snapshot, 200
