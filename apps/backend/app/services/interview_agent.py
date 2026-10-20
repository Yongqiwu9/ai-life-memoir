"""Owner-scoped offline Agent orchestration with durable, revocable request reservations."""

import hashlib
import hmac
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.exceptions import AGENT_SAFE_ERRORS, AppException
from app.crud import interview_agent as crud
from app.crud import interview_message as message_crud
from app.models.interview_agent import InterviewAgentState, InterviewAgentTurn
from app.schemas.interview_agent import (
    CONTRACT_VERSION,
    LEGACY_CONTRACT_VERSION,
    MAX_QUESTIONS,
    MOCK_POLICY_VERSION,
    AgentStateRead,
    AgentTurnCreate,
    AgentTurnRead,
    AskedQuestion,
    QuestionRequest,
    QuestionResult,
)
from app.services.ai_interview_client import (
    InterviewAIClient,
    ProcessingDecision,
    normalize_question,
)


def _error(code: str):
    status, message = AGENT_SAFE_ERRORS.get(code, AGENT_SAFE_ERRORS["AGENT_INTERNAL_ERROR"])
    return AppException(
        message,
        code=code if code in AGENT_SAFE_ERRORS else "AGENT_INTERNAL_ERROR",
        status_code=status,
    )


def _rollback(db):
    try:
        db.rollback()
    except Exception:  # noqa: BLE001 - sanitize storage/policy/provider failures
        raise _error("AGENT_STORAGE_UNAVAILABLE") from None


def _owned(db, user_id, session_id, *, lock=False):
    record = crud.owned_session(db, user_id, session_id, lock=lock)
    if record is None:
        raise _error("NOT_FOUND")
    if crud.get_integration_profile(db, session_id) is not None:
        raise _error("AGENT_STATE_CONFLICT")
    return record


def _read(turn):
    return AgentTurnRead.model_validate(turn)


def _fingerprint(user_id, session_id, data):
    payload = {
        "actor_user_id": str(user_id),
        "session_id": str(session_id),
        "contract_version": data.contract_version,
        "action": data.action,
        "expected_version": data.expected_version,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).digest()


def _require(decision, user_id, session_id, ids):
    try:
        decision.require(
            user_id=user_id, session_id=session_id, source_ids=list(dict.fromkeys(ids))
        )
    except AppException as exc:
        code = (
            exc.code
            if exc.code in {"PROCESSING_DENIED", "POLICY_UNAVAILABLE"}
            else "POLICY_UNAVAILABLE"
        )
        raise _error(code) from None
    except Exception:  # noqa: BLE001 - sanitize storage/policy/provider failures
        raise _error("POLICY_UNAVAILABLE") from None


def _asked_ids(turn):
    values = turn.asked_question_message_ids
    if not isinstance(values, list) or len(values) > MAX_QUESTIONS:
        raise _error("SOURCE_UNAVAILABLE")
    ids = []
    for value in values:
        try:
            parsed = UUID(value) if type(value) is str else None
        except (ValueError, TypeError, AttributeError):
            raise _error("SOURCE_UNAVAILABLE") from None
        if parsed is None or str(parsed) != value or parsed in ids:
            raise _error("SOURCE_UNAVAILABLE")
        ids.append(parsed)
    return tuple(ids)


def _source_reference(db, session_id, turn):
    if turn.context_present is False:
        if turn.context_scope_id is not None or turn.context_message_id is not None:
            raise _error("SOURCE_UNAVAILABLE")
        return None
    if turn.context_present is not True or turn.context_scope_id is None:
        raise _error("SOURCE_UNAVAILABLE")
    if turn.context_message_id != turn.context_scope_id:
        raise _error("SOURCE_UNAVAILABLE")
    ref = crud.message_reference(db, session_id, turn.context_scope_id)
    if ref is None or ref.role != "user" or ref.source != "text":
        raise _error("SOURCE_UNAVAILABLE")
    return ref


def _closure(db, session_id, roots, *, context=None):
    """Resolve only IDs/roles/order, never historical source bodies.

    Each question remembers its entire Provider input dependency closure, including
    a neutral question's supplied source. SET NULL never repairs these stable IDs.
    """
    visited, visiting, permissions = set(), set(), []
    if context is not None:
        permissions.append(context.id)

    def visit(output_id):
        if output_id in visiting:
            raise _error("SOURCE_UNAVAILABLE")
        if output_id in visited:
            return crud.message_reference(db, session_id, output_id)
        if len(visited) + len(visiting) >= MAX_QUESTIONS:
            raise _error("SOURCE_UNAVAILABLE")
        turn = crud.question_turn_for_output(db, session_id, output_id)
        ref = crud.message_reference(db, session_id, output_id)
        if turn is None or ref is None or turn.output_message_id != output_id:
            raise _error("SOURCE_UNAVAILABLE")
        if ref.role != "assistant" or ref.source != "ai_generated":
            raise _error("SOURCE_UNAVAILABLE")
        visiting.add(output_id)
        source = _source_reference(db, session_id, turn)
        if source is not None:
            if source.sequence >= ref.sequence:
                raise _error("SOURCE_UNAVAILABLE")
            permissions.append(source.id)
        for parent_id in _asked_ids(turn):
            parent = visit(parent_id)
            if parent is None or parent.sequence >= ref.sequence:
                raise _error("SOURCE_UNAVAILABLE")
        visiting.remove(output_id)
        visited.add(output_id)
        permissions.append(output_id)
        return ref

    for root in roots:
        visit(root)
    return list(dict.fromkeys(permissions))


def _request_from_turn(db, user_id, session_id, state, turn, decision):
    source = _source_reference(db, session_id, turn)
    asked_ids = _asked_ids(turn)
    permissions = _closure(db, session_id, asked_ids, context=source)
    _require(decision, user_id, session_id, permissions)
    text = None if source is None else crud.message_content(db, session_id, source.id)
    questions = []
    for message_id in asked_ids:
        historical = crud.question_turn_for_output(db, session_id, message_id)
        body = crud.message_content(db, session_id, message_id)
        if historical is None:
            raise _error("SOURCE_UNAVAILABLE")
        questions.append(
            {
                "message_id": message_id,
                "question_key": historical.question_key,
                "text": body,
            }
        )
    try:
        return QuestionRequest(
            request_id=turn.id,
            session_id=session_id,
            policy_version=state.policy_version,
            agent_version=turn.reserved_version,
            generation_epoch=turn.reserved_epoch,
            context_message_ids=() if source is None else (source.id,),
            context_text=text,
            asked_questions=tuple(AskedQuestion.model_validate(item) for item in questions),
        )
    except (ValidationError, ValueError, TypeError):
        raise _error("SOURCE_UNAVAILABLE") from None


def _select_request(db, user_id, session_id, state, turn_id, decision):
    source = crud.latest_text_reference(db, session_id)
    # This also requires a policy decision for a neutral, source-free question.
    _require(decision, user_id, session_id, [] if source is None else [source.id])
    ids = []
    turns = crud.question_turns(db, session_id)
    if len(turns) >= MAX_QUESTIONS:
        raise _error("AGENT_QUESTION_LIMIT")
    for old in turns:
        if old.output_scope_id is None or old.output_message_id is None:
            continue
        try:
            permissions = _closure(db, session_id, [old.output_scope_id])
            _require(decision, user_id, session_id, permissions)
        except AppException as exc:
            if exc.code in {"SOURCE_UNAVAILABLE", "PROCESSING_DENIED"}:
                continue
            raise
        ids.append(old.output_scope_id)
    draft = InterviewAgentTurn(
        id=turn_id,
        context_present=source is not None,
        context_message_id=None if source is None else source.id,
        context_scope_id=None if source is None else source.id,
        asked_question_message_ids=[str(value) for value in ids],
        reserved_version=state.version,
        reserved_epoch=state.generation_epoch,
    )
    return _request_from_turn(db, user_id, session_id, state, draft, decision)


def get_state(db: Session, user_id: UUID, session_id: UUID, decision=None):
    session = _owned(db, user_id, session_id)
    state = crud.get_state(db, session_id)
    if state is None:
        if crud.has_history(db, session_id):
            raise _error("AGENT_STATE_UNAVAILABLE")
        return AgentStateRead(
            session_id=session_id,
            contract_version=CONTRACT_VERSION,
            status="idle",
            version=0,
            generation_epoch=0,
            session_status=session.status,
        )
    pending = crud.pending_turns(db, session_id)
    if len(pending) > 1:
        raise _error("AGENT_STATE_UNAVAILABLE")
    return AgentStateRead(
        session_id=session_id,
        contract_version=state.contract_version,
        status=state.status,
        version=state.version,
        generation_epoch=state.generation_epoch,
        session_status=session.status,
        pending_turn_id=pending[0].id if pending else None,
        current_question_message_id=state.current_question_message_id,
    )


def get_turn(db: Session, user_id: UUID, session_id: UUID, turn_id: UUID):
    _owned(db, user_id, session_id)
    turn = crud.get_turn(db, session_id, turn_id)
    if turn is None:
        raise _error("NOT_FOUND")
    return _read(turn)


def _replay(db, user_id, session_id, turn, fingerprint, decision):
    if turn.actor_user_id != user_id or not hmac.compare_digest(
        turn.request_fingerprint, fingerprint
    ):
        raise _error("IDEMPOTENCY_CONFLICT")
    if turn.execution_status == "pending":
        return _read(turn), 202
    if turn.execution_status == "failed":
        raise _error(turn.failure_code)
    if turn.execution_status == "discarded":
        raise _error("AGENT_RESULT_DISCARDED")
    if turn.execution_status != "completed":
        raise _error("AGENT_STATE_UNAVAILABLE")
    if turn.contract_version != CONTRACT_VERSION:
        raise _error("LEGACY_AGENT_SESSION")
    if turn.result_kind == "control":
        return _read(turn), 200
    if turn.result_kind == "question":
        if turn.output_message_id is None or turn.output_scope_id != turn.output_message_id:
            raise _error("IDEMPOTENCY_RESULT_UNAVAILABLE")
        try:
            permissions = _closure(db, session_id, [turn.output_scope_id])
        except AppException:
            raise _error("IDEMPOTENCY_RESULT_UNAVAILABLE") from None
    elif turn.result_kind == "no_question":
        source = _source_reference(db, session_id, turn)
        permissions = _closure(db, session_id, _asked_ids(turn), context=source)
    else:
        raise _error("AGENT_STATE_UNAVAILABLE")
    _require(decision, user_id, session_id, permissions)
    return _read(turn), 200


def _commit(db, user_id, session_id, key, fingerprint, decision):
    """An ambiguous commit never authorizes another Provider call.

    Readback is independent. Missing records are not proof of rollback; pending
    records are metadata-only 202; confirmed completed results follow replay gates.
    """
    try:
        db.commit()
        return None
    except Exception:  # noqa: BLE001 - sanitize storage/policy/provider failures
        _rollback(db)
        try:
            with Session(bind=db.get_bind(), expire_on_commit=False) as verification:
                _owned(verification, user_id, session_id)
                turn = crud.find_turn(verification, session_id, key)
                if turn is None:
                    raise _error("AGENT_COMMIT_UNCERTAIN")
                result = _replay(verification, user_id, session_id, turn, fingerprint, decision)
                return result
        except AppException:
            raise
        except Exception:  # noqa: BLE001 - sanitize storage/policy/provider failures
            raise _error("AGENT_COMMIT_UNCERTAIN") from None


def _new_turn(user_id, session_id, data, key, fingerprint, state, *, turn_id=None):
    return InterviewAgentTurn(
        id=turn_id or uuid4(),
        session_id=session_id,
        actor_user_id=user_id,
        idempotency_key=key,
        contract_version=CONTRACT_VERSION,
        action=data.action,
        request_fingerprint=fingerprint,
        reserved_version=state.version,
        reserved_epoch=state.generation_epoch,
        execution_status="pending",
        context_present=False,
        asked_question_message_ids=[],
    )


def _complete(turn, state, kind):
    now = datetime.now(UTC)
    turn.execution_status = "completed"
    turn.result_kind = kind
    turn.result_state_contract_version = state.contract_version
    turn.resulting_status = state.status
    turn.resulting_version = state.version
    turn.finished_at = now
    turn.updated_at = now


def _discard(turn, reason):
    if turn.execution_status == "pending":
        turn.execution_status = "discarded"
        turn.discard_reason = reason
        turn.finished_at = datetime.now(UTC)
        turn.updated_at = turn.finished_at


def _control(db, user_id, session_id, session, state, data, key, fingerprint, decision, legacy):
    transitions = {
        "start": ("idle", "listening"),
        "pause": ("listening", "paused"),
        "resume": ("paused", "listening"),
    }
    if data.action == "end":
        if state.status == "ended" and state.contract_version != LEGACY_CONTRACT_VERSION:
            raise _error("AGENT_STATE_CONFLICT")
    else:
        previous, _target = transitions[data.action]
        if legacy or state.status != previous:
            raise _error("AGENT_STATE_CONFLICT")
    turn = _new_turn(user_id, session_id, data, key, fingerprint, state)
    turn.execution_status = "completed"
    if data.action == "end":
        state.status = "ended"
        state.current_question_message_id = None
        session.status = "completed"
        session.ended_at = datetime.now(UTC)
    else:
        state.status = transitions[data.action][1]
    state.version += 1
    if data.action != "start":
        state.generation_epoch += 1
    state.updated_at = datetime.now(UTC)
    if data.action in {"pause", "end"}:
        for pending in crud.pending_turns(db, session_id):
            _discard(pending, "AGENT_PAUSED" if data.action == "pause" else "SESSION_ENDED")
    _complete(turn, state, "control")
    crud.add_flush(db, turn)
    result = _read(turn), 201
    recovered = _commit(db, user_id, session_id, key, fingerprint, decision)
    return recovered or result


def _reserve(db, user_id, session_id, data, key, fingerprint, decision, client):
    session = _owned(db, user_id, session_id, lock=True)
    existing = crud.find_turn(db, session_id, key)
    if existing is not None:
        result = _replay(db, user_id, session_id, existing, fingerprint, decision)
        db.rollback()  # Release read locks; no mutation on a replay.
        return None, result
    if session.status != "active":
        raise _error("SESSION_NOT_ACTIVE")
    state = crud.get_state(db, session_id)
    if state is None:
        if crud.has_history(db, session_id):
            raise _error("AGENT_STATE_UNAVAILABLE")
        state = InterviewAgentState(
            session_id=session_id,
            contract_version=CONTRACT_VERSION,
            status="idle",
            version=0,
            generation_epoch=0,
            policy_version=MOCK_POLICY_VERSION,
        )
        db.add(state)
    has_legacy_turn = crud.has_legacy_turn(db, session_id)
    if state.contract_version == CONTRACT_VERSION and has_legacy_turn:
        raise _error("AGENT_STATE_UNAVAILABLE")
    legacy = state.contract_version == LEGACY_CONTRACT_VERSION
    if legacy and data.action != "end":
        raise _error("LEGACY_AGENT_SESSION")
    if state.version != data.expected_version:
        raise _error("AGENT_VERSION_CONFLICT")
    if data.action != "request_question":
        return None, _control(
            db, user_id, session_id, session, state, data, key, fingerprint, decision, legacy
        )
    if state.status != "listening":
        raise _error("AGENT_STATE_CONFLICT")
    if crud.pending_turns(db, session_id):
        raise _error("AGENT_GENERATION_PENDING")
    if state.policy_version != MOCK_POLICY_VERSION:
        raise _error("POLICY_UNAVAILABLE")
    _require(decision, user_id, session_id, [])
    # Server-only allowlist, not client-selected and no fallback for an unknown adapter.
    if getattr(client, "provider_id", None) != "mock":
        raise _error("AI_UNAVAILABLE")
    turn_id = uuid4()
    request = _select_request(db, user_id, session_id, state, turn_id, decision)
    turn = _new_turn(user_id, session_id, data, key, fingerprint, state, turn_id=turn_id)
    turn.provider_id = "mock"
    turn.context_present = bool(request.context_message_ids)
    turn.context_message_id = (
        request.context_message_ids[0] if request.context_message_ids else None
    )
    turn.context_scope_id = turn.context_message_id
    turn.asked_question_message_ids = [str(item.message_id) for item in request.asked_questions]
    crud.add_flush(db, turn)
    recovered = _commit(db, user_id, session_id, key, fingerprint, decision)
    return (None, recovered) if recovered else (request, None)


def _finish_failure(db, user_id, session_id, turn_id, code):
    """Best effort terminal evidence; never replace a committed discard/result."""
    _rollback(db)
    try:
        if crud.owned_session(db, user_id, session_id, lock=True) is None:
            db.rollback()
            return
        turn = crud.get_turn(db, session_id, turn_id)
        if turn is None or turn.execution_status != "pending":
            db.rollback()
            return
        turn.execution_status = "failed"
        turn.failure_code = code
        turn.finished_at = datetime.now(UTC)
        turn.updated_at = turn.finished_at
        db.flush()
        db.commit()
    except Exception:  # noqa: BLE001 - sanitize storage/policy/provider failures
        _rollback(db)
        # Leave an unfinished reservation. GET and explicit pause/end remain available.
        raise _error("AGENT_STORAGE_UNAVAILABLE") from None


def _publish(db, user_id, session_id, request, result, key, fingerprint, decision):
    session = crud.owned_session(db, user_id, session_id, lock=True)
    if session is None:
        raise _error("NOT_FOUND")
    state = crud.get_state(db, session_id)
    turn = crud.get_turn(db, session_id, request.request_id)
    if turn is None:
        raise _error("AGENT_STATE_UNAVAILABLE")
    if turn.execution_status != "pending":
        replay = _replay(db, user_id, session_id, turn, fingerprint, decision)
        db.rollback()
        return replay
    reason = None
    if (
        state is None
        or state.contract_version != CONTRACT_VERSION
        or session.status != "active"
        or state.status != "listening"
        or state.version != request.agent_version
        or state.generation_epoch != request.generation_epoch
    ):
        reason = "STATE_CHANGED"
    elif state.policy_version != request.policy_version:
        reason = "POLICY_CHANGED"
    else:
        try:
            current = _request_from_turn(db, user_id, session_id, state, turn, decision)
            if current != request:
                reason = "SOURCE_CHANGED"
        except AppException:
            reason = "SOURCE_UNAVAILABLE"
    if reason:
        _discard(turn, reason)
        db.flush()
        recovered = _commit(db, user_id, session_id, key, fingerprint, decision)
        if recovered is not None:
            return recovered
        raise _error("AGENT_RESULT_DISCARDED")
    if result.outcome == "question":
        used = crud.question_turns(db, session_id)
        if len(used) >= MAX_QUESTIONS:
            raise _error("AGENT_QUESTION_LIMIT")
        if result.question_key in {item.question_key for item in used}:
            raise _error("AI_INVALID_RESPONSE")
        normalized = normalize_question(result.question)
        if normalized in {normalize_question(item.text) for item in request.asked_questions}:
            raise _error("AI_INVALID_RESPONSE")
        message = message_crud.create_message_flush(
            db,
            session_id=session_id,
            role="assistant",
            source="ai_generated",
            content=result.question,
        )
        # The common parent lock orders all three message-writing paths.
        for asked in request.asked_questions:
            ref = crud.message_reference(db, session_id, asked.message_id)
            if ref is None or ref.sequence >= message.sequence:
                raise _error("SOURCE_UNAVAILABLE")
        turn.output_message_id = message.id
        turn.output_scope_id = message.id
        turn.question_key = result.question_key
        state.current_question_message_id = message.id
        state.version += 1
        state.updated_at = datetime.now(UTC)
        _complete(turn, state, "question")
    else:
        _complete(turn, state, "no_question")
    db.flush()
    read = _read(turn), 201
    recovered = _commit(db, user_id, session_id, key, fingerprint, decision)
    return recovered or read


def advance_with_status(
    db: Session,
    user_id: UUID,
    session_id: UUID,
    data: AgentTurnCreate,
    idempotency_key: UUID,
    decision: ProcessingDecision,
    client: InterviewAIClient,
):
    fingerprint = _fingerprint(user_id, session_id, data)
    try:
        request, early = _reserve(
            db,
            user_id,
            session_id,
            data,
            idempotency_key,
            fingerprint,
            decision,
            client,
        )
    except AppException:
        _rollback(db)
        raise
    except Exception:  # noqa: BLE001 - sanitize storage/policy/provider failures
        _rollback(db)
        raise _error("AGENT_STORAGE_UNAVAILABLE") from None
    if early is not None:
        return early
    # No ORM objects or expired attributes cross this transaction boundary.
    try:
        if db.in_transaction():
            raise _error("AGENT_STORAGE_UNAVAILABLE")
        raw = client.next_question(request)
        result = QuestionResult.model_validate(raw).validate_binding(request)
    except TimeoutError:
        failure = _error("AI_PROVIDER_TIMEOUT")
    except AppException as exc:
        failure = _error(
            exc.code
            if exc.code in {"AI_UNAVAILABLE", "AI_PROVIDER_TIMEOUT"}
            else "AI_INVALID_RESPONSE"
        )
    except (ValidationError, ValueError, TypeError, AttributeError):
        failure = _error("AI_INVALID_RESPONSE")
    except Exception:  # noqa: BLE001 - sanitize storage/policy/provider failures
        failure = _error("AI_UNAVAILABLE")
    else:
        try:
            return _publish(
                db, user_id, session_id, request, result, idempotency_key, fingerprint, decision
            )
        except AppException as exc:
            if exc.code in {"AGENT_COMMIT_UNCERTAIN", "AGENT_RESULT_DISCARDED", "NOT_FOUND"}:
                _rollback(db)
                raise
            failure = _error(exc.code)
        except Exception:  # noqa: BLE001 - sanitize storage/policy/provider failures
            failure = _error("AGENT_STORAGE_UNAVAILABLE")
    _finish_failure(db, user_id, session_id, request.request_id, failure.code)
    raise failure from None


def advance(db: Session, *args, **kwargs):
    return advance_with_status(db, *args, **kwargs)[0]
