"""Owner-scoped durable synthetic commands around the independent C1 service."""

import copy
import hmac
from datetime import UTC, datetime
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crud import dialogue as crud
from app.crud import interview_agent as agent_crud
from app.crud import interview_message as message_crud
from app.models.dialogue_runtime import AgentDependency, AgentEffect, AgentSource
from app.models.family_member import FamilyMember
from app.models.interview import Interview
from app.models.interview_agent import InterviewAgentState, InterviewAgentTurn
from app.models.interview_message import InterviewMessage
from app.schemas import dialogue as c
from app.services import dialogue_checkpoint as checkpoint
from app.services.dialogue_client import checked_reply
from app.services.dialogue_policy import Runtime, error


def now():
    return datetime.now(UTC)


def owned(db, actor, session_id, *, lock=False):
    session = agent_crud.owned_session(db, actor, session_id, lock=lock)
    if session is None:
        raise error("NOT_FOUND", 404)
    return session


def scope_for(db, actor, session):
    member_id, family_id = db.execute(
        select(Interview.family_member_id, FamilyMember.family_id)
        .join(FamilyMember, Interview.family_member_id == FamilyMember.id)
        .where(Interview.id == session.interview_id)
    ).one()
    return c.DialogueScope(
        actor_user_id=actor,
        family_id=family_id,
        family_member_id=member_id,
        interview_id=session.interview_id,
        session_id=session.id,
    )


def _key(runtime):
    if runtime.integrity is None:
        raise error("DIALOGUE_INTEGRITY_UNAVAILABLE", 503)
    return runtime.integrity


def _state(db, actor, session_id, runtime, *, create=False):
    session = owned(db, actor, session_id, lock=True)
    state = crud.state(db, session_id, lock=True)
    if state is None and create:
        runtime.require(actor, session_id)
        if db.scalar(
            select(InterviewMessage.id).where(InterviewMessage.session_id == session_id).limit(1)
        ) is not None or crud.turns(db, session_id):
            raise error("LEGACY_AGENT_SESSION")
        if session.status != "active":
            raise error("SESSION_NOT_ACTIVE")
        state = InterviewAgentState(
            session_id=session_id,
            contract_version=c.STORAGE_VERSION,
            status="idle",
            version=0,
            generation_epoch=0,
            policy_version=runtime.policy.version,
            integration_profile=c.PROFILE,
            persistence_version=0,
            stop_fence=0,
            last_applied_event_seq=0,
            next_command_order=1,
            checkpoint_status="sync_required",
            effective_mode=runtime.policy.mode,
            clock_origin_at=now(),
        )
        crud.add_flush(db, state)
    if state is None or state.integration_profile != c.PROFILE:
        raise error("LEGACY_AGENT_SESSION")
    return session, state


def read_command(db, actor, session_id, command_id):
    owned(db, actor, session_id)
    turn = crud.turn(db, session_id, turn_id=command_id)
    if turn is None or turn.actor_user_id != actor or turn.integration_profile != c.PROFILE:
        raise error("COMMAND_OUTCOME_UNKNOWN", 503)
    return _read(turn)


def _read(turn):
    result = turn.result_metadata or {}
    return c.CommandRead(
        id=turn.id,
        session_id=turn.session_id,
        execution_status=turn.execution_status,
        message_id=UUID(result["message_id"]) if result.get("message_id") else None,
        response_id=UUID(result["response_id"]) if result.get("response_id") else None,
        resulting_version=turn.resulting_version,
        code=result.get("code", "QUEUED"),
    )


def _commit(db, actor, session_id, turn_id):
    try:
        db.commit()
        return None
    except Exception:  # noqa: BLE001 - uncertain commit must never authorize another call
        try:
            db.rollback()
            bind = db.get_bind()
            engine = getattr(bind, "engine", bind)
            with Session(engine) as verification:
                return read_command(verification, actor, session_id, turn_id)
        except Exception:  # noqa: BLE001 - no exception/body disclosure
            raise error("COMMAND_OUTCOME_UNKNOWN", 503) from None


def _finish(turn, state, code="OK", *, status="completed", applied_seq=None, **metadata):
    turn.execution_status = status
    turn.finished_at = now()
    turn.applied_event_seq = applied_seq
    turn.resulting_version = state.persistence_version if status == "completed" else None
    turn.resulting_status = state.status if status == "completed" else None
    turn.result_state_contract_version = c.STORAGE_VERSION if status == "completed" else None
    turn.result_kind = "control" if status == "completed" else None
    turn.result_metadata = {**(turn.result_metadata or {}), "code": code, **metadata}


def _new_turn(db, actor, state, key, kind, payload, fingerprint):
    turn = InterviewAgentTurn(
        id=uuid4(),
        session_id=state.session_id,
        actor_user_id=actor,
        idempotency_key=key,
        contract_version=c.STORAGE_VERSION,
        action=kind,
        event_kind=kind,
        integration_profile=c.PROFILE,
        execution_status="queued",
        request_fingerprint=fingerprint,
        fingerprint_key_id=payload.pop("_key_id"),
        command_payload=payload,
        command_order=state.next_command_order,
        event_id=uuid4(),
        transition_attempts=[],
    )
    state.next_command_order += 1
    crud.add_flush(db, turn)
    return turn


def _fingerprint(actor, session_id, operation, data):
    return {
        "actor": str(actor),
        "session": str(session_id),
        "operation": operation,
        "profile": c.PROFILE,
        "request": data.model_dump(mode="json"),
    }


def _existing(db, actor, session_id, key, fingerprint, runtime):
    turn = crud.turn(db, session_id, key=key)
    if turn is None:
        return None
    if turn.actor_user_id != actor or turn.integration_profile != c.PROFILE:
        raise error("IDEMPOTENCY_CONFLICT")
    signature = _key(runtime).sign(fingerprint, turn.fingerprint_key_id)
    if not hmac.compare_digest(signature, turn.request_fingerprint):
        raise error("IDEMPOTENCY_CONFLICT")
    result = _read(turn)
    db.rollback()
    return result


def _fence(db, state, kind):
    state.stop_fence += 1
    state.persistence_version += 1
    state.active_command_id = None
    state.checkpoint_status = "sync_required"
    for turn in crud.turns(db, state.session_id):
        if turn.execution_status not in {"queued", "preparing"}:
            continue
        safety_control = turn.event_kind in {"pause", "typing_started"} or (
            turn.event_kind == "set_mode" and turn.command_payload.get("mode") == "record_only"
        )
        if kind != "end" and (turn.event_kind == "user_message_committed" or safety_control):
            turn.execution_status = "queued"
            if turn.event_envelope:
                attempts = copy.deepcopy(turn.transition_attempts)
                attempts[-1]["outcome"] = "superseded"
                turn.transition_attempts = attempts
                turn.event_envelope = None
            continue
        _finish(turn, state, "SUPERSEDED", status="discarded")
    for effect in crud.effects(db, state.session_id):
        if effect.stop_fence >= state.stop_fence:
            continue
        if effect.status in {"reserved", "claimed", "ready", "published"}:
            effect.status = "discarded"
            effect.finished_at = now()
        effect.token_digest = None


def submit(db, actor, session_id, data: c.CommandCreate, key: UUID, runtime: Runtime):
    try:
        owned(db, actor, session_id, lock=True)
        fp = _fingerprint(actor, session_id, "command", data)
        replay = _existing(db, actor, session_id, key, fp, runtime)
        if replay is not None:
            return replay
        session, state = _state(db, actor, session_id, runtime, create=data.action == "start")
        safety = data.action in {"pause", "end", "typing_started"} or (
            data.action == "set_mode" and data.mode == "record_only"
        )
        if data.expected_version != state.persistence_version and not (
            safety and data.expected_version < state.persistence_version
        ):
            raise error("DIALOGUE_VERSION_CONFLICT")
        if data.action != "end" and state.status == "ended":
            raise error("SESSION_NOT_ACTIVE")
        if state.status == "blocked" and data.action != "end":
            raise error("DIALOGUE_STATE_UNAVAILABLE")
        if state.status == "idle" and data.action not in {"start", "pause", "end", "set_mode"}:
            raise error("START_REQUIRED")
        if not safety:
            runtime.require(actor, session_id)
        if data.topic_key is not None:
            header = crud.checkpoint(db, session_id)
            allowed = {
                r["topic_key"]
                for r in (header.metadata_json.get("question_receipts", []) if header else [])
            }
            if data.topic_key not in allowed:
                raise error("DIALOGUE_INVALID_REQUEST", 422)
        noop = (data.action == "pause" and state.status in {"idle", "paused"}) or (
            data.action == "end" and state.status == "ended"
        )
        if safety and not noop:
            _fence(db, state, data.action)
        if data.action == "pause" and state.status == "idle":
            for pending in crud.turns(db, session_id):
                if pending.event_kind == "start" and pending.execution_status in {
                    "queued",
                    "preparing",
                }:
                    _finish(pending, state, "SUPERSEDED", status="discarded")
            state.active_command_id = None
        if data.action == "pause" and state.status == "paused":
            # A repeated stop is still a no-op for core versions/fences, but it
            # revokes any older resume that has not published under this lock.
            for pending in crud.turns(db, session_id):
                if pending.event_kind == "resume" and pending.execution_status in {
                    "queued",
                    "preparing",
                }:
                    if pending.transition_attempts:
                        attempts = copy.deepcopy(pending.transition_attempts)
                        attempts[-1]["outcome"] = "superseded"
                        pending.transition_attempts = attempts
                    _finish(pending, state, "SUPERSEDED", status="discarded")
                    if state.active_command_id == pending.id:
                        state.active_command_id = None
        payload = {k: v for k, v in data.model_dump(mode="json").items() if k != "expected_version"}
        payload["accepted_ms"] = 0 if safety else runtime.allocation.elapsed_ms(session_id)
        payload["_key_id"] = _key(runtime).current
        turn = _new_turn(db, actor, state, key, data.action, payload, _key(runtime).sign(fp))
        if noop:
            _finish(turn, state, "NOT_STARTED" if state.status == "idle" else "ALREADY_STOPPED")
        elif data.action == "end":
            state.status = "ended"
            state.checkpoint_status = "unavailable"
            session.status = "completed"
            session.ended_at = now()
            crud.purge_checkpoint(db, session_id)
            _finish(turn, state)
        elif data.action == "pause":
            state.status = "paused"
        elif data.action == "set_mode" and data.mode == "record_only":
            state.effective_mode = "record_only"
        db.flush()
        result, turn_id = _read(turn), turn.id
        return _commit(db, actor, session_id, turn_id) or result
    except Exception:
        db.rollback()
        raise


def save_text(db, actor, session_id, data: c.TextCreate, key: UUID, runtime: Runtime):
    try:
        owned(db, actor, session_id, lock=True)
        fp = _fingerprint(actor, session_id, "message", data)
        replay = _existing(db, actor, session_id, key, fp, runtime)
        if replay is not None:
            return replay
        session, state = _state(db, actor, session_id, runtime)
        runtime.require(actor, session_id)
        if session.status != "active" or state.status in {"idle", "blocked", "ended"}:
            raise error(
                "START_REQUIRED" if state.status == "idle" else "DIALOGUE_STATE_UNAVAILABLE"
            )
        if data.expected_version != state.persistence_version:
            raise error("DIALOGUE_VERSION_CONFLICT")
        checkpoint.source_gate(db, actor, session_id, runtime)
        _fence(db, state, "user_message_committed")
        message = message_crud.create_message_flush(
            db, session_id=session_id, role="user", source="text", content=data.content
        )
        crud.add_flush(
            db,
            AgentSource(
                session_id=session_id,
                stable_message_id=message.id,
                live_message_id=message.id,
                message_sequence=message.sequence,
                origin="user_text",
                source_role="user",
                version_ordinal=1,
                fingerprint=c.source_fingerprint(data.content),
                availability="available",
            ),
        )
        payload = {
            "message_id": str(message.id),
            "human_turn_id": str(data.human_turn_id),
            "accepted_ms": runtime.allocation.elapsed_ms(session_id),
            "_key_id": _key(runtime).current,
        }
        turn = _new_turn(
            db, actor, state, key, "user_message_committed", payload, _key(runtime).sign(fp)
        )
        turn.result_metadata = {"message_id": str(message.id), "code": "INPUT_SAVED_QUEUED"}
        result, turn_id = _read(turn), turn.id
        return _commit(db, actor, session_id, turn_id) or result
    except Exception:
        db.rollback()
        raise


def _wire(
    operation, state, scope, context, runtime, *, core=None, event=None, effect=None, call_id
):
    values = {
        "operation": operation,
        "call_id": call_id,
        "scope": scope,
        "persistence_version": state.persistence_version,
        "stop_fence": state.stop_fence,
        "context": context,
        "policy": core.policy if core else runtime.policy,
        "state": core,
        "event": event,
        "effect": effect,
    }
    temporary = {**values, "profile": c.PROFILE, "kernel_version": c.CONTRACT_VERSION}
    return c.WireRequest(**values, input_digest=c.canonical_digest(temporary))


def _call(db, client, request):
    if db.in_transaction():
        raise error("DIALOGUE_TRANSACTION_BOUNDARY", 500)
    return checked_reply(request, client.call(request))


def _bootstrap(db, actor, session_id, root_id, runtime, client):
    session, state = _state(db, actor, session_id, runtime)
    if crud.checkpoint(db, session_id) is not None:
        return
    runtime.require(actor, session_id)
    turn = crud.turn(db, session_id, turn_id=root_id)
    if (
        turn.event_kind not in {"start", "set_mode"}
        or state.status != "idle"
        or state.active_command_id not in {None, root_id}
    ):
        raise error("START_REQUIRED")
    scope = scope_for(db, actor, session)
    context = checkpoint.context_value(
        scope, 1, uuid5(session_id, "manifest:1"), 1, [], [], [], [], []
    )
    checkpoint.pin_context(db, context)
    state.current_context_revision = 1
    state.active_command_id = root_id
    request = _wire(
        "initialize", state, scope, context, runtime, call_id=uuid5(root_id, "initialize")
    )
    token = (state.persistence_version, state.stop_fence)
    if _commit(db, actor, session_id, root_id) is not None:
        raise error("COMMAND_OUTCOME_UNKNOWN", 503)
    try:
        reply = _call(db, client, request)
    except Exception:  # noqa: BLE001 - initialize is pure; only explicit retry may resend
        raise error("DIALOGUE_TRANSITION_PENDING", 503) from None
    _, state = _state(db, actor, session_id, runtime)
    if (
        (state.persistence_version, state.stop_fence) != token
        or state.active_command_id != root_id
        or state.status != "idle"
    ):
        db.rollback()
        raise error("DIALOGUE_VERSION_CONFLICT")
    checkpoint.source_gate(db, actor, session_id, runtime)
    if reply.initial_state.scope != scope or reply.initial_state.policy != runtime.policy:
        raise error("DIALOGUE_INVALID_RESPONSE", 502)
    checkpoint.save(db, state, reply.initial_state, runtime)
    state.checkpoint_status = "valid"
    if _commit(db, actor, session_id, root_id) is not None:
        raise error("COMMAND_OUTCOME_UNKNOWN", 503)


def _ref(scope, source):
    return c.SourceVersionRef(
        kind="message",
        entity_id=source.stable_message_id,
        version_id=source.stable_message_id,
        version=1,
        origin="user_text",
        source_scope=c.SourceScope(
            owner_user_id=scope.actor_user_id,
            family_id=scope.family_id,
            family_member_id=scope.family_member_id,
            origin_interview_id=scope.interview_id,
            origin_session_id=scope.session_id,
        ),
    )


def _context_next(db, actor, core, runtime, *, message_id=None, refresh=False):
    bindings = checkpoint.source_gate(db, actor, core.scope.session_id, runtime)
    allowed = {r.entity_id for r in core.committed_refs}
    if message_id:
        allowed.add(message_id)
    sources, history = [], []
    for binding in bindings:
        if binding.stable_message_id not in allowed:
            continue
        body = crud.message_body(db, core.scope.session_id, binding.stable_message_id)
        if body is None or c.source_fingerprint(body) != binding.fingerprint:
            raise error("SOURCE_UNAVAILABLE")
        ref = _ref(core.scope, binding)
        sources.append(
            c.FixtureSource(
                ref=ref,
                text=body,
                availability="available",
                revision_fingerprint=binding.fingerprint,
            )
        )
        history.append(
            c.HistoryItem(sequence=binding.message_sequence, ref=ref, role="user", text=body)
        )
    receipts = {r.response_id: r for r in core.question_receipts}
    for effect in crud.effects(db, core.scope.session_id):
        if effect.kind != "deliver" or effect.output_stable_id is None:
            continue
        if effect.output_message_id is None:
            raise error("SOURCE_UNAVAILABLE")
        meta = crud.message_metadata(db, core.scope.session_id, effect.output_message_id)
        body = crud.message_body(db, core.scope.session_id, effect.output_message_id)
        if (
            meta is None
            or meta.role != "assistant"
            or body is None
            or c.source_fingerprint(body) != effect.binding_json.get("output_fingerprint")
        ):
            raise error("SOURCE_UNAVAILABLE")
        receipt = receipts.get(effect.response_id)
        delivery = receipt.delivery if receipt else effect.binding_json.get("delivery", "started")
        history.append(
            c.HistoryItem(
                sequence=meta.sequence,
                role="assistant",
                text=body,
                response_id=effect.response_id,
                delivery=delivery,
            )
        )
    history.sort(key=lambda x: x.sequence)
    omitted = history[: -core.policy.max_history_items]
    summaries = [
        c.SummaryEntry(
            label="topic", quote=c.SourceQuote(ref=x.ref, start=0, end=len(x.text), text=x.text)
        )
        for x in omitted
        if x.role == "user"
    ]
    manifest_version = core.manifest_version + int(refresh)
    return checkpoint.context_value(
        core.scope,
        core.context_revision + 1,
        uuid5(core.scope.session_id, "manifest:" + str(manifest_version)),
        manifest_version,
        sources,
        history[-core.policy.max_history_items :],
        summaries,
        list(dict.fromkeys(r.question_key for r in core.question_receipts)),
        core.skipped_keys,
    )


def _payload(turn, core, context):
    data = turn.command_payload
    kind = turn.event_kind
    internal = {
        "delivery_started": c.DeliveryStartedPayload,
        "delivery_completed": c.DeliveryCompletedPayload,
        "response_failed": c.FailurePayload,
    }
    if kind in internal:
        return checkpoint.decode(internal[kind], data["payload"])
    if kind == "context_refresh":
        return c.ReplaceSelectionPayload(context=context)
    if kind == "user_message_committed":
        ref = next(r for r in context.source_refs if str(r.entity_id) == data["message_id"])
        return c.UserMessageCommittedPayload(
            human_turn_id=UUID(data["human_turn_id"]), message_ref=ref, semantic_hint="unknown"
        )
    choices = {
        "start": c.StartPayload,
        "pause": c.PausePayload,
        "resume": c.ResumePayload,
        "typing_started": c.TypingStartedPayload,
        "typing_ended": c.TypingEndedPayload,
        "request_response": c.RequestResponsePayload,
    }
    if kind in choices:
        return choices[kind]()
    if kind == "set_mode":
        return c.SetModePayload(mode=data["mode"])
    if kind in {"skip_topic", "unskip_topic"}:
        return (c.SkipTopicPayload if kind == "skip_topic" else c.UnskipTopicPayload)(
            topic_key=data["topic_key"]
        )
    if kind == "silence_elapsed":
        return c.SilenceElapsedPayload(
            human_turn_id=UUID(data["human_turn_id"]), silence_cycle=data["silence_cycle"]
        )
    raise error("DIALOGUE_INVALID_REQUEST", 422)


def _effect_rows(db, state, turn, transition, runtime):
    for effect in transition.effects:
        if isinstance(effect, c.ErrorEffect):
            continue
        if isinstance(effect, c.CancelGenerationEffect | c.StopPlaybackEffect):
            for old in crud.effects(db, state.session_id):
                if old.request_id == effect.request_id and old.status in {
                    "reserved",
                    "claimed",
                    "ready",
                    "published",
                }:
                    old.status, old.finished_at, old.token_digest = "discarded", now(), None
                    if old.kind == "deliver" and old.output_stable_id is not None:
                        old.binding_json = {**old.binding_json, "delivery": "interrupted"}
        existing = db.get(AgentEffect, effect.effect_id)
        if existing is not None:
            raise error("DIALOGUE_EFFECT_CONFLICT")
        delivery = effect.response if isinstance(effect, c.DeliverEffect) else None
        request_id = delivery.request_id if delivery else effect.request_id
        body = (
            effect.model_dump(mode="json")
            if delivery is None
            else {
                "kind": "deliver",
                "effect_id": str(effect.effect_id),
                "request_id": str(delivery.request_id),
                "response_id": str(delivery.response_id),
                **c.generation_binding(delivery),
            }
        )
        if delivery is not None:
            # generation_binding contains UUID values; persist only its JSON form.
            body = {
                "kind": "deliver",
                "effect_id": str(effect.effect_id),
                "request_id": str(delivery.request_id),
                "response_id": str(delivery.response_id),
                **{k: delivery.model_dump(mode="json")[k] for k in c.GENERATION_BINDING_FIELDS},
            }
        row = AgentEffect(
            id=effect.effect_id,
            session_id=state.session_id,
            origin_turn_id=turn.id,
            request_id=request_id,
            kind=effect.kind,
            epoch=transition.next_state.epoch,
            stop_fence=state.stop_fence,
            context_revision=transition.next_state.context_revision,
            status="reserved" if effect.kind == "generate" else "completed",
            binding_json=body,
            dispatch_outcome="not_sent",
            finished_at=None if effect.kind == "generate" else now(),
        )
        if effect.kind == "deliver":
            row.status, row.finished_at = "ready", None
            row.response_id = delivery.response_id
            expires = (
                runtime.allocation.elapsed_ms(state.session_id) + runtime.delivery_token_ttl_ms
            )
            token = runtime.integrity.token(
                turn.actor_user_id,
                state.session_id,
                delivery.response_id,
                state.stop_fence,
                expires,
            )
            row.binding_json = {
                **body,
                "expires_ms": expires,
                "token_key_id": runtime.integrity.current,
            }
            row.token_digest = runtime.digest_token(token)
        crud.add_flush(db, row)
        refs = (
            effect.dependency_refs
            if isinstance(effect, c.GenerateEffect)
            else transition.next_state.context_source_refs
        )
        for ref in dict.fromkeys(refs):
            db.add(
                AgentDependency(
                    session_id=state.session_id,
                    source_message_id=ref.entity_id,
                    owner_kind="effect",
                    effect_id=row.id,
                )
            )


def _block(db, state, code):
    _fence(db, state, "source_restricted")
    state.status = "blocked"
    state.checkpoint_status = "unavailable"
    crud.purge_checkpoint(db, state.session_id)
    db.commit()
    raise error(code)


def _transition(db, actor, session_id, turn_id, root_id, runtime, client, *, supplied=None):
    _, state = _state(db, actor, session_id, runtime)
    turn = crud.turn(db, session_id, turn_id=turn_id)
    if turn is None or turn.actor_user_id != actor:
        raise error("COMMAND_OUTCOME_UNKNOWN", 503)
    if turn.execution_status in {"completed", "failed", "discarded"}:
        result = _read(turn)
        db.rollback()
        return result
    if state.status in {"blocked", "ended"} or state.active_command_id not in {None, root_id}:
        raise error("DIALOGUE_STATE_UNAVAILABLE")
    try:
        core = checkpoint.load(db, actor, state, runtime)
        context = checkpoint.restore_context(db, actor, core.scope, core.context_revision, runtime)
        pinned = turn.transition_attempts[-1].get("context") if turn.transition_attempts else None
        if turn.execution_status == "preparing" and pinned is not None:
            context = checkpoint.restore_context(
                db, actor, core.scope, pinned["revision"], runtime, pinned=pinned
            )
            if str(context.id) != pinned["context_id"]:
                raise error("DIALOGUE_CONTEXT_UNAVAILABLE")
        elif turn.event_kind == "user_message_committed":
            message_id = UUID(turn.command_payload["message_id"])
            if any(r.entity_id == message_id for r in core.committed_refs):
                _finish(turn, state, "ALREADY_APPLIED")
                if state.active_command_id == root_id:
                    state.active_command_id = None
                db.flush()
                result = _read(turn)
                db.commit()
                return result
            context = _context_next(db, actor, core, runtime, message_id=message_id)
        elif turn.event_kind == "context_refresh":
            context = _context_next(db, actor, core, runtime, refresh=True)
        payload = supplied or _payload(turn, core, context)
    except Exception as exc:
        if getattr(exc, "code", None) in {
            "SOURCE_UNAVAILABLE",
            "DIALOGUE_CHECKPOINT_UNAVAILABLE",
            "DIALOGUE_CONTEXT_UNAVAILABLE",
            "DIALOGUE_INTEGRITY_FAILURE",
        }:
            _block(db, state, "SOURCE_UNAVAILABLE")
        raise
    state.active_command_id = root_id
    if turn.execution_status == "preparing":
        old = turn.event_envelope
        if (
            state.persistence_version != turn.reserved_persistence_version
            or state.stop_fence != turn.reserved_stop_fence
        ):
            raise error("DIALOGUE_VERSION_CONFLICT")
        hydrated = copy.deepcopy(old)
        if hydrated.get("payload", {}).get("context") is not None:
            hydrated["payload"]["context"] = context.model_dump(mode="json")
        event = checkpoint.decode(c.Event, hydrated)
        if event.payload != payload:
            raise error("DIALOGUE_VERSION_CONFLICT")
    else:
        state.persistence_version += 1
        ordinal = len(turn.transition_attempts) + 1
        event = c.Event(
            event_id=uuid5(turn.event_id, f"transition:{ordinal}"),
            seq=core.last_seq + 1,
            time_ms=max(core.last_time_ms, turn.command_payload.get("accepted_ms", 0)),
            scope=core.scope,
            expected_version=core.version,
            payload=payload,
        )
        # Generation response bodies exist only in this transient RPC, never event journals.
        if supplied is None or not isinstance(supplied, c.ReadyPayload):
            envelope = event.model_dump(mode="json")
            if envelope["payload"].get("context") is not None:
                envelope["payload"]["context"] = checkpoint.context_descriptor(context)
            turn.event_envelope = envelope
        else:
            turn.event_envelope = None
        turn.transition_attempts = [
            *turn.transition_attempts,
            {
                "ordinal": ordinal,
                "event_id": str(event.event_id),
                "seq": event.seq,
                "time_ms": event.time_ms,
                "core_version": core.version,
                "context_id": str(context.id),
                "context": checkpoint.context_descriptor(context),
                "input_digest": c.canonical_digest(event),
                "fence": state.stop_fence,
                "outcome": "preparing",
            },
        ]
        turn.execution_status = "preparing"
        turn.reserved_event_seq = event.seq
        turn.reserved_persistence_version = state.persistence_version
        turn.reserved_stop_fence = state.stop_fence
    request = _wire(
        "transition",
        state,
        core.scope,
        context,
        runtime,
        core=core,
        event=event,
        call_id=uuid5(event.event_id, "transition-rpc"),
    )
    token = (state.persistence_version, state.stop_fence, state.active_command_id)
    db.flush()
    recovered = _commit(db, actor, session_id, turn_id)
    if recovered is not None:
        return recovered
    try:
        reply = _call(db, client, request)
    except Exception:  # noqa: BLE001 - keep pending without disclosing wire data
        # Preparing remains durable. Only explicit apply may retry a pure event.
        raise error("DIALOGUE_TRANSITION_PENDING", 503) from None
    _, state = _state(db, actor, session_id, runtime)
    turn = crud.turn(db, session_id, turn_id=turn_id)
    if (
        state.persistence_version,
        state.stop_fence,
        state.active_command_id,
    ) != token or turn.execution_status != "preparing":
        # Retire only this stale reservation; never clear a newer coordinator.
        if turn.execution_status == "preparing" and turn.reserved_persistence_version == token[0]:
            _finish(turn, state, "SUPERSEDED", status="discarded")
            if state.active_command_id == root_id:
                state.active_command_id = None
            db.commit()
        else:
            db.rollback()
        return read_command(db, actor, session_id, turn_id)
    checkpoint.source_gate(db, actor, session_id, runtime)
    transition = reply.transition
    if transition.next_state.scope != core.scope or transition.next_state.policy != core.policy:
        raise error("DIALOGUE_INVALID_RESPONSE", 502)
    if (
        state.status == "paused"
        and turn.event_kind
        in {"user_message_committed", "typing_started", "typing_ended", "context_refresh"}
        and any(x.kind in {"generate", "deliver"} for x in transition.effects)
    ):
        raise error("DIALOGUE_INVALID_RESPONSE", 502)
    if transition.next_state.version not in {core.version, core.version + 1}:
        raise error("DIALOGUE_INVALID_RESPONSE", 502)
    applied = transition.next_state.version == core.version + 1
    if applied:
        if transition.next_state.last_seq != event.seq:
            raise error("DIALOGUE_INVALID_RESPONSE", 502)
        checkpoint.pin_context(db, context)
        if turn.event_kind == "delivery_started":
            response = core.ready_response
            effect = next(
                (
                    x
                    for x in crud.effects(db, session_id)
                    if x.kind == "deliver" and x.response_id == response.response_id
                ),
                None,
            )
            if (
                effect is None
                or effect.status != "ready"
                or effect.stop_fence != state.stop_fence
                or effect.output_stable_id is not None
            ):
                raise error("DIALOGUE_DELIVERY_UNAVAILABLE")
            message = message_crud.create_message_flush(
                db, session_id=session_id, role="assistant", source="text", content=response.text
            )
            effect.output_message_id = effect.output_stable_id = message.id
            effect.status = "published"
            effect.binding_json = {
                **effect.binding_json,
                "output_fingerprint": c.source_fingerprint(response.text),
                "delivery": "started",
            }
            turn.result_metadata = {
                **(turn.result_metadata or {}),
                "output_message_id": str(message.id),
            }
            for generated in crud.effects(db, session_id):
                if (
                    generated.kind == "generate"
                    and generated.request_id == response.request_id
                    and generated.status == "ready"
                ):
                    generated.status, generated.finished_at = "completed", now()
        elif turn.event_kind == "delivery_completed":
            effect = next(
                (
                    x
                    for x in crud.effects(db, session_id)
                    if x.kind == "deliver" and x.response_id == payload.receipt.response_id
                ),
                None,
            )
            if effect is not None and effect.status == "published":
                effect.status, effect.finished_at = "completed", now()
                effect.binding_json = {**effect.binding_json, "delivery": "delivered"}
        checkpoint.save(db, state, transition.next_state, runtime)
        # Backend stops remain effective while earlier non-generative events drain.
        # Only explicit resume/light-mode commands release their respective latch.
        paused = state.status == "paused" and turn.event_kind != "resume"
        record_only = state.effective_mode == "record_only" and not (
            turn.event_kind == "set_mode" and turn.command_payload.get("mode") == "light"
        )
        state.status = (
            "paused"
            if paused and transition.next_state.status not in {"paused", "blocked", "ended"}
            else transition.next_state.status
        )
        state.effective_mode = "record_only" if record_only else transition.next_state.mode
        state.checkpoint_status = (
            "valid"
            if state.status == transition.next_state.status
            and state.effective_mode == transition.next_state.mode
            else "sync_required"
        )
        _effect_rows(db, state, turn, transition, runtime)
    if isinstance(payload, c.ReadyPayload | c.FailurePayload):
        # Callback checkpoint, deliver effect and generate outcome are one commit.
        # A delivery can never observe a ready response with a still-claimed generator.
        generated = next(
            (
                x
                for x in crud.effects(db, session_id)
                if x.kind == "generate" and x.request_id == payload.request_id
            ),
            None,
        )
        if (
            generated is None
            or generated.stop_fence != state.stop_fence
            or generated.status != "claimed"
        ):
            raise error("DIALOGUE_EFFECT_NOT_DISPATCHABLE")
        ready = (
            applied
            and isinstance(payload, c.ReadyPayload)
            and (
                transition.next_state.ready_response is not None
                and transition.next_state.ready_response.response_id == payload.response.response_id
            )
        )
        generated.status = "ready" if ready else "completed"
        generated.response_id = (
            payload.response.response_id if isinstance(payload, c.ReadyPayload) else None
        )
        generated.finished_at = None if ready else now()
    code = transition.result.code
    status = "completed" if transition.result.disposition != "rejected" else "failed"
    attempts = copy.deepcopy(turn.transition_attempts)
    attempts[-1]["outcome"] = "applied" if applied else "rejected"
    turn.transition_attempts = attempts
    _finish(
        turn,
        state,
        code,
        status=status,
        applied_seq=event.seq if applied else None,
        **(
            {"response_id": str(transition.result.response_id)}
            if transition.result.response_id
            else {}
        ),
    )
    if turn.parent_turn_id is None:
        state.active_command_id = None
    db.flush()
    result = _read(turn)
    return _commit(db, actor, session_id, turn_id) or result


def apply_command(db, actor, session_id, turn_id, data, key, runtime, client):
    """Bind public apply to the original command and a stable application payload."""
    try:
        _, state = _state(db, actor, session_id, runtime)
        root = crud.turn(db, session_id, turn_id=turn_id)
        if root is None or root.actor_user_id != actor or root.parent_turn_id is not None:
            raise error("COMMAND_OUTCOME_UNKNOWN", 503)
        signature = (
            _key(runtime)
            .sign(
                _fingerprint(actor, session_id, "apply:" + str(turn_id), data),
                root.fingerprint_key_id,
            )
            .hex()
        )
        bound = (root.result_metadata or {}).get("apply_fingerprint")
        bound_key = (root.result_metadata or {}).get("apply_key")
        if bound_key is not None and bound_key != str(key):
            raise error("IDEMPOTENCY_CONFLICT")
        if bound is not None and not hmac.compare_digest(bound, signature):
            raise error("IDEMPOTENCY_CONFLICT")
        if bound is None:
            if data.expected_version != state.persistence_version:
                raise error("DIALOGUE_VERSION_CONFLICT")
            if root.execution_status in {"completed", "failed", "discarded"}:
                result = _read(root)
                db.rollback()
                return result
            root.result_metadata = {
                **(root.result_metadata or {}),
                "apply_fingerprint": signature,
                "apply_key": str(key),
            }
            recovered = _commit(db, actor, session_id, turn_id)
            if recovered is not None:
                return recovered
        else:
            db.rollback()
        return apply(db, actor, session_id, turn_id, runtime, client)
    except Exception:
        db.rollback()
        raise


def apply(db, actor, session_id, turn_id, runtime, client):
    """Explicit, ordered application. Replays do not dispatch a Provider."""
    try:
        _, state = _state(db, actor, session_id, runtime)
        runtime.require(actor, session_id)
        root = crud.turn(db, session_id, turn_id=turn_id)
        if root is None or root.actor_user_id != actor or root.parent_turn_id is not None:
            raise error("COMMAND_OUTCOME_UNKNOWN", 503)
        if root.execution_status in {"completed", "failed", "discarded"}:
            result = _read(root)
            db.rollback()
            return result
        earlier = [
            x
            for x in crud.turns(db, session_id)
            if x.parent_turn_id is None
            and x.command_order < root.command_order
            and x.execution_status in {"queued", "preparing"}
        ]
        non_generative = {
            "pause",
            "typing_started",
            "typing_ended",
            "set_mode",
            "user_message_committed",
        }
        # Explicit apply/resume synchronizes retained controls and input in original order.
        if (
            root.event_kind in non_generative | {"resume"}
            and earlier
            and all(x.event_kind in non_generative for x in earlier)
        ) or (
            root.event_kind == "start"
            and earlier
            and all(x.event_kind == "set_mode" for x in earlier)
        ):
            ids = [x.id for x in sorted(earlier, key=lambda x: x.command_order)]
            db.rollback()
            for prior_id in ids:
                prior = apply(db, actor, session_id, prior_id, runtime, client)
                if prior.execution_status != "completed":
                    return read_command(db, actor, session_id, turn_id)
            _, state = _state(db, actor, session_id, runtime)
        elif earlier and root.event_kind not in {"pause", "typing_started", "set_mode"}:
            raise error("DIALOGUE_QUEUE_PENDING")
        if crud.checkpoint(db, session_id) is None:
            db.rollback()
            _bootstrap(db, actor, session_id, turn_id, runtime, client)
            _, state = _state(db, actor, session_id, runtime)
        root = crud.turn(db, session_id, turn_id=turn_id)
        if root.event_kind in {"request_response", "silence_elapsed"}:
            if state.checkpoint_status != "valid" or state.status != "listening":
                raise error("DIALOGUE_STATE_UNAVAILABLE")
            core = checkpoint.load(db, actor, state, runtime)
            old_context = checkpoint.restore_context(
                db, actor, core.scope, core.context_revision, runtime
            )
            fresh = _context_next(db, actor, core, runtime, refresh=True)
            changed = (
                fresh.recent_history != old_context.recent_history
                or fresh.asked_keys != old_context.asked_keys
                or fresh.skipped_keys != old_context.skipped_keys
                or fresh.summary_entries != old_context.summary_entries
            )
            if changed:
                child = next(
                    (x for x in crud.turns(db, session_id) if x.parent_turn_id == turn_id), None
                )
                if child is None:
                    child_key = uuid5(turn_id, "context_refresh")
                    if crud.turn(db, session_id, key=child_key) is not None:
                        raise error("IDEMPOTENCY_CONFLICT")
                    child = _new_turn(
                        db,
                        actor,
                        state,
                        child_key,
                        "context_refresh",
                        {
                            "_key_id": _key(runtime).current,
                            "accepted_ms": runtime.allocation.elapsed_ms(session_id),
                            "origin": "published_history_refresh",
                        },
                        _key(runtime).sign([str(turn_id), "context_refresh"]),
                    )
                    child.parent_turn_id, child.internal_reason = (
                        turn_id,
                        "published_history_refresh",
                    )
                child_id = child.id
                state.active_command_id = turn_id
                db.commit()
                result = _transition(db, actor, session_id, child_id, turn_id, runtime, client)
                if result.execution_status != "completed":
                    _, current = _state(db, actor, session_id, runtime)
                    parent = crud.turn(db, session_id, turn_id=turn_id)
                    if (
                        result.execution_status in {"failed", "discarded"}
                        and parent.execution_status == "queued"
                    ):
                        _finish(parent, current, "CONTEXT_REFRESH_UNAVAILABLE", status="discarded")
                        if current.active_command_id == turn_id:
                            current.active_command_id = None
                        db.commit()
                    else:
                        db.rollback()
                    return read_command(db, actor, session_id, turn_id)
        db.rollback()
        return _transition(db, actor, session_id, turn_id, turn_id, runtime, client)
    except Exception:
        db.rollback()
        raise


def dispatch(db, actor, session_id, effect_id, runtime, client):
    """Explicit claim-once synthetic effect execution. Never called by GET/replay."""
    try:
        _, state = _state(db, actor, session_id, runtime)
        runtime.require(actor, session_id)
        effect = db.get(AgentEffect, effect_id)
        if effect is None or effect.session_id != session_id or effect.kind != "generate":
            raise error("NOT_FOUND", 404)
        if effect.status != "reserved":
            raise error("DIALOGUE_EFFECT_NOT_DISPATCHABLE")
        if (
            state.checkpoint_status != "valid"
            or state.active_command_id is not None
            or state.stop_fence != effect.stop_fence
        ):
            raise error("DIALOGUE_STATE_UNAVAILABLE")
        core = checkpoint.load(db, actor, state, runtime)
        if core.pending_effect is None or core.pending_effect.effect_id != effect_id:
            raise error("DIALOGUE_EFFECT_NOT_DISPATCHABLE")
        context = checkpoint.restore_context(
            db, actor, core.scope, effect.context_revision, runtime
        )
        effect.status, effect.dispatch_outcome, effect.claimed_at = "claimed", "sent", now()
        request = _wire(
            "generate",
            state,
            core.scope,
            context,
            runtime,
            effect=core.pending_effect,
            call_id=uuid5(effect_id, "generate-rpc"),
        )
        fence = state.stop_fence
        origin_id = effect.origin_turn_id
        db.flush()
        recovered = _commit(db, actor, session_id, origin_id)
        if recovered is not None:
            return recovered
        try:
            reply = _call(db, client, request)
        except Exception:  # noqa: BLE001 - preserve unknown without disclosing transport data
            observe_unknown(db, actor, session_id, effect_id, runtime)
            raise error("DIALOGUE_GENERATION_UNKNOWN", 503) from None
        _, state = _state(db, actor, session_id, runtime)
        effect = db.get(AgentEffect, effect_id)
        effect.dispatch_outcome, effect.observed_at = "returned", now()
        if state.stop_fence != fence or effect.status != "claimed":
            effect.observation_code = "LATE_RESULT_IGNORED"
            db.commit()
            return read_command(db, actor, session_id, origin_id)
        if reply.generation is None:
            raise error("DIALOGUE_INVALID_RESPONSE", 502)
        callback_id = uuid5(effect_id, "response-callback")
        key = uuid5(effect_id, "response-key")
        if crud.turn(db, session_id, key=key) is not None:
            raise error("IDEMPOTENCY_CONFLICT")
        turn = _new_turn(
            db,
            actor,
            state,
            key,
            reply.generation.kind,
            {
                "_key_id": _key(runtime).current,
                "accepted_ms": runtime.allocation.elapsed_ms(session_id),
            },
            _key(runtime).sign([str(effect_id), reply.generation.kind]),
        )
        turn.event_id = callback_id
        callback_turn_id = turn.id
        # Persist no ready response/raw provider packet in the command journal.
        if isinstance(reply.generation, c.FailurePayload):
            turn.command_payload = {
                **turn.command_payload,
                "payload": reply.generation.model_dump(mode="json"),
            }
        db.commit()
        try:
            result = _transition(
                db,
                actor,
                session_id,
                callback_turn_id,
                callback_turn_id,
                runtime,
                client,
                supplied=reply.generation,
            )
        except Exception:
            observe_unknown(db, actor, session_id, effect_id, runtime)
            raise
        if result.execution_status in {"queued", "preparing"}:
            # A callback commit that cannot be reconciled is not permission to retry.
            observe_unknown(db, actor, session_id, effect_id, runtime)
        return result
    except Exception:
        db.rollback()
        raise


def observe_unknown(db, actor, session_id, effect_id, runtime):
    """Record an old dispatch observation without changing a newer publication authority."""
    _, state = _state(db, actor, session_id, runtime)
    effect = db.get(AgentEffect, effect_id)
    if effect is None or effect.session_id != session_id:
        raise error("NOT_FOUND", 404)
    effect.dispatch_outcome, effect.observed_at = "unknown", now()
    effect.observation_code = "DISPATCH_OUTCOME_UNKNOWN"
    if effect.stop_fence != state.stop_fence or effect.status in {
        "discarded",
        "completed",
        "failed",
    }:
        db.commit()
        return
    _fence(db, state, "generation_unknown")
    effect.status, effect.finished_at = "unknown", now()
    state.status, state.checkpoint_status = "blocked", "unavailable"
    crud.purge_checkpoint(db, session_id)
    db.commit()


def read_state(db, actor, session_id, runtime):
    session = owned(db, actor, session_id)
    state = crud.state(db, session_id)
    if state is None or state.integration_profile != c.PROFILE:
        raise error("NOT_FOUND", 404)
    values = {
        "session_id": session_id,
        "effective_status": state.status,
        "persistence_version": state.persistence_version,
        "core_version": state.version,
        "epoch": state.generation_epoch,
        "stop_fence": state.stop_fence,
        "checkpoint_sync": state.checkpoint_status,
        "session_status": session.status,
        "queued_command_ids": tuple(
            x.id
            for x in crud.turns(db, session_id)
            if x.actor_user_id == actor
            and x.parent_turn_id is None
            and x.execution_status in {"queued", "preparing"}
        ),
    }
    if state.checkpoint_status == "valid" and state.status == "ready" and runtime.integrity:
        checkpoint.source_gate(db, actor, session_id, runtime)
        effect = next(
            (
                x
                for x in crud.effects(db, session_id)
                if x.kind == "deliver" and x.status == "ready" and x.stop_fence == state.stop_fence
            ),
            None,
        )
        if effect is not None:
            expires = effect.binding_json["expires_ms"]
            if runtime.allocation.elapsed_ms(session_id) <= expires:
                token = runtime.integrity.sign(
                    [
                        str(actor),
                        str(session_id),
                        str(effect.response_id),
                        state.stop_fence,
                        expires,
                    ],
                    effect.binding_json["token_key_id"],
                ).hex()
                values.update(
                    ready_response_id=effect.response_id,
                    delivery_token=token,
                    delivery_expires_ms=expires,
                )
    return c.StateRead(**values)


def deliver(db, actor, session_id, response_id, data, key, runtime, client, *, complete=False):
    try:
        session, state = _state(db, actor, session_id, runtime)
        operation = "delivery_complete" if complete else "delivery_start"
        fp = _fingerprint(actor, session_id, operation + ":" + str(response_id), data)
        replay = _existing(db, actor, session_id, key, fp, runtime)
        if replay is not None:
            return c.DeliveryRead(command=replay)
        runtime.require(actor, session_id)
        checkpoint.source_gate(db, actor, session_id, runtime)
        if (
            state.checkpoint_status != "valid"
            or session.status != "active"
            or data.expected_version != state.persistence_version
        ):
            raise error("DIALOGUE_VERSION_CONFLICT")
        effect = next(
            (
                x
                for x in crud.effects(db, session_id)
                if x.kind == "deliver" and x.response_id == response_id
            ),
            None,
        )
        if (
            effect is None
            or effect.stop_fence != state.stop_fence
            or effect.token_digest is None
            or not hmac.compare_digest(effect.token_digest, runtime.digest_token(data.token))
            or runtime.allocation.elapsed_ms(session_id) > effect.binding_json["expires_ms"]
            or effect.status != ("published" if complete else "ready")
        ):
            raise error("DIALOGUE_DELIVERY_UNAVAILABLE")
        core = checkpoint.load(db, actor, state, runtime)
        response = core.active_response if complete else core.ready_response
        if response is None or response.response_id != response_id:
            raise error("DIALOGUE_DELIVERY_UNAVAILABLE")
        receipt = c.DeliveryReceipt(
            request_id=response.request_id,
            response_id=response_id,
            policy_version=response.policy_version,
            epoch=response.epoch,
            context_id=response.context_id,
            context_revision=response.context_revision,
            manifest_id=response.manifest_id,
            manifest_version=response.manifest_version,
            kind="completed" if complete else "started",
        )
        payload = (c.DeliveryCompletedPayload if complete else c.DeliveryStartedPayload)(
            receipt=receipt
        )
        turn = _new_turn(
            db,
            actor,
            state,
            key,
            payload.kind,
            {
                "_key_id": _key(runtime).current,
                "accepted_ms": runtime.allocation.elapsed_ms(session_id),
                "payload": payload.model_dump(mode="json"),
            },
            _key(runtime).sign(fp),
        )
        turn_id, fence = turn.id, state.stop_fence
        db.commit()
        result = _transition(db, actor, session_id, turn_id, turn_id, runtime, client)
        if complete or result.execution_status != "completed":
            return c.DeliveryRead(command=result)
        _, state = _state(db, actor, session_id, runtime)
        checkpoint.source_gate(db, actor, session_id, runtime)
        effect = db.get(AgentEffect, uuid5(response.request_id, "deliver"))
        if (
            state.stop_fence != fence
            or state.status != "delivering"
            or effect is None
            or effect.output_message_id is None
        ):
            db.rollback()
            return c.DeliveryRead(command=result)
        body = crud.message_body(db, session_id, effect.output_message_id)
        message_id = effect.output_message_id
        db.rollback()
        return c.DeliveryRead(command=result, output_message_id=message_id, text=body)
    except Exception:
        db.rollback()
        raise


def restrict_source(db, actor, session_id, message_id, runtime):
    """Trusted harness method only; not registered as a Consent HTTP endpoint."""
    _, state = _state(db, actor, session_id, runtime)
    runtime.require(actor, session_id)
    source = db.get(AgentSource, (session_id, message_id))
    if source is None:
        raise error("NOT_FOUND", 404)
    source.availability = "restricted"
    _fence(db, state, "source_restricted")
    state.status, state.checkpoint_status = "blocked", "unavailable"
    crud.purge_checkpoint(db, session_id)
    db.commit()


def submit_silence(db, actor, session_id, runtime):
    """Explicit trusted test-clock driver, never a client clock or background scheduler."""
    _, state = _state(db, actor, session_id, runtime)
    core = checkpoint.load(db, actor, state, runtime)
    if core.current_human_turn_id is None:
        raise error("DIALOGUE_STATE_UNAVAILABLE")
    key = uuid4()
    turn = _new_turn(
        db,
        actor,
        state,
        key,
        "silence_elapsed",
        {
            "_key_id": _key(runtime).current,
            "human_turn_id": str(core.current_human_turn_id),
            "silence_cycle": core.silence_cycle,
            "accepted_ms": runtime.allocation.elapsed_ms(session_id),
        },
        _key(runtime).sign([str(key), "silence_elapsed"]),
    )
    result = _read(turn)
    db.commit()
    return result
