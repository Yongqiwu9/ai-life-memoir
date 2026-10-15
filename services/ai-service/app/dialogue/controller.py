"""Pure, ordered decisions for the explicitly synthetic, single-instance profile.

Effects are instructions, not evidence of provider cancellation or audio delivery.
The caller consumes only effects of a new transition, never effects of a replay.
"""

from uuid import uuid5

from pydantic import ValidationError

from app.dialogue import contracts as c
from app.dialogue.context import validate_context
from app.dialogue.runner import validate_response


def _updated(value, **changes):
    # model_copy(update=...) would bypass nested and cross-field validation.
    return type(value).model_validate({**value.model_dump(), **changes})


def _context_fields(context: c.ContextSnapshot) -> dict:
    return {
        "context_id": context.id,
        "context_revision": context.context_revision,
        "context_digest": c.canonical_digest(context),
        "context_source_refs": context.source_refs,
        "selection_refs": context.selection_refs,
        "manifest_id": context.manifest_id,
        "manifest_version": context.manifest_version,
    }


def create_state(
    scope: c.DialogueScope, policy: c.Policy, context: c.ContextSnapshot
) -> c.DialogueState:
    """Initialize fixture state without an implicit start or an opening question."""
    try:
        scope = c.DialogueScope.model_validate(scope)
        policy = c.Policy.model_validate(policy)
        if context.scope != scope:
            raise c.DialogueError("INVALID_EVENT")
        context = validate_context(context, policy)
        revisions = tuple(
            c.SourceRevisionReceipt(
                ref=source.ref, revision_fingerprint=source.revision_fingerprint
            )
            for source in context.sources
        )
        if len(revisions) >= policy.max_events:
            raise c.DialogueError("CONTEXT_LIMIT")
        return c.DialogueState(
            scope=scope,
            policy=policy,
            mode=policy.mode,
            skipped_keys=context.skipped_keys,
            known_source_revisions=revisions,
            **_context_fields(context),
        )
    except c.DialogueError:
        raise
    except (ValidationError, TypeError, ValueError, AttributeError):
        raise c.DialogueError("INVALID_EVENT") from None


def _reject(state: c.DialogueState, code="INVALID_EVENT") -> c.Transition:
    return c.Transition(
        next_state=state,
        effects=(),
        result=c.ResultMetadata(code=code, disposition="rejected"),
    )


def _invalidate(state: c.DialogueState, **changes) -> tuple[c.DialogueState, tuple]:
    effects = []
    if state.pending_effect is not None:
        request = state.pending_effect.request_id
        effects.append(
            c.CancelGenerationEffect(
                effect_id=uuid5(request, "cancel_generation"), request_id=request
            )
        )
    # A ready result might already be queued by a future delivery adapter.
    response = state.active_response or state.ready_response
    if response is not None:
        effects.append(
            c.StopPlaybackEffect(
                effect_id=uuid5(response.request_id, "stop_playback"),
                request_id=response.request_id,
                response_id=response.response_id,
            )
        )
    receipts = state.question_receipts
    if state.active_response is not None:
        receipts = tuple(
            _updated(receipt, delivery="interrupted")
            if receipt.response_id == state.active_response.response_id
            and receipt.delivery == "started"
            else receipt
            for receipt in receipts
        )
    target = "paused" if state.status == "paused" else "listening"
    if state.status == "idle":
        target = "idle"
    return (
        _updated(
            state,
            epoch=state.epoch + 1,
            pending_effect=None,
            ready_response=None,
            active_response=None,
            question_receipts=receipts,
            status=target,
            **changes,
        ),
        tuple(effects),
    )


def _receipt(event: c.Event, result: c.ResultMetadata) -> c.EventReceipt:
    return c.EventReceipt(
        event_id=event.event_id,
        digest=c.canonical_digest(event),
        seq=event.seq,
        result=result,
    )


def _accept(
    before: c.DialogueState,
    after: c.DialogueState,
    event: c.Event,
    effects=(),
    result: c.ResultMetadata | None = None,
    *,
    terminal=False,
) -> c.Transition:
    result = result or c.ResultMetadata()
    receipt = _receipt(event, result)
    changes = {
        "version": before.version + 1,
        "last_seq": event.seq,
        "last_time_ms": event.time_ms,
    }
    if terminal:
        changes["terminal_receipt"] = receipt
    else:
        changes["event_receipts"] = (*before.event_receipts, receipt)
    return c.Transition(
        next_state=_updated(after, **changes), effects=tuple(effects), result=result
    )


def _ignored(state, event):
    return _accept(
        state, state, event, result=c.ResultMetadata(code="IGNORED", disposition="ignored")
    )


def _block(state, event, code, *, ordered):
    next_state, effects = _invalidate(state)
    next_state = _updated(next_state, status="blocked")
    result = c.ResultMetadata(code=code, disposition="blocked")
    effects = (*effects, c.ErrorEffect(code=code))
    if len(state.event_receipts) < state.policy.max_events:
        if ordered:
            return _accept(state, next_state, event, effects, result)
        next_state = _updated(
            next_state,
            version=state.version + 1,
            event_receipts=(*state.event_receipts, _receipt(event, result)),
        )
    else:
        next_state = _updated(next_state, version=state.version + 1)
    return c.Transition(next_state=next_state, effects=effects, result=result)


def _at_capacity(state: c.DialogueState, *, extra_events=0, **counts) -> bool:
    ledgers = (
        "turn_cycles",
        "committed_refs",
        "restricted_refs",
        "known_requests",
        "question_receipts",
        "known_source_revisions",
        "skipped_keys",
    )
    return len(state.event_receipts) + extra_events >= state.policy.max_events or any(
        counts.get(name, len(getattr(state, name))) >= state.policy.max_events for name in ledgers
    )


def _same_context(state, context):
    metadata_matches = (
        context.scope == state.scope
        and context.id == state.context_id
        and context.context_revision == state.context_revision
        and context.manifest_id == state.manifest_id
        and context.manifest_version == state.manifest_version
        and context.source_refs == state.context_source_refs
        and context.selection_refs == state.selection_refs
    )
    if not metadata_matches:
        return False
    if _restricted_dependencies(state, context):
        # Controls can stop or collect input without reopening quarantined text.
        # Every generation/delivery path performs the restriction check first.
        return True
    return c.canonical_digest(context) == state.context_digest


def _history_request(state, item):
    return next(
        (
            known
            for known in state.known_requests
            if uuid5(known.request_id, "response") == item.response_id
        ),
        None,
    )


def _restricted_dependencies(state, context):
    """Inspect only provenance metadata, including dependencies of older AI text."""
    if not state.restricted_refs:
        return False
    restricted = set(state.restricted_refs)
    if restricted.intersection(context.source_refs):
        return True
    for item in context.recent_history:
        if item.role == "assistant":
            known = _history_request(state, item)
            if known is None or restricted.intersection(known.dependency_refs):
                return True
    return False


def _dependency_refs(state, context):
    # Ancestors remain cancellation dependencies even after their raw text is
    # removed from a selection. They do not grant access to any extra body.
    refs = list(context.source_refs)
    for item in context.recent_history:
        if item.role == "assistant":
            known = _history_request(state, item)
            refs.extend(
                known.dependency_refs
                if known is not None
                else (entry.ref for entry in state.known_source_revisions)
            )
    return tuple(dict.fromkeys(refs))


def _available(state, context):
    # The restriction ledger is checked before any source body is inspected.
    if _restricted_dependencies(state, context):
        raise c.DialogueError("SOURCE_UNAVAILABLE")
    validate_context(context, state.policy)


def _adopt_context(state, context, *, committed_ref=None, replace=False):
    if context.scope != state.scope:
        raise c.DialogueError("INVALID_EVENT")
    if context.context_revision != state.context_revision + 1:
        raise c.DialogueError("INVALID_EVENT")
    if replace:
        if context.manifest_version != state.manifest_version + 1:
            raise c.DialogueError("INVALID_EVENT")
    else:
        if (
            context.manifest_id != state.manifest_id
            or context.manifest_version != state.manifest_version
            or context.selection_refs != state.selection_refs
            or committed_ref not in context.source_refs
        ):
            raise c.DialogueError("INVALID_EVENT")
        expected_refs = set(state.context_source_refs).difference(state.restricted_refs)
        expected_refs.add(committed_ref)
        if set(context.source_refs) != expected_refs:
            raise c.DialogueError("INVALID_EVENT")
    if _restricted_dependencies(state, context):
        raise c.DialogueError("SOURCE_UNAVAILABLE")
    revisions = list(state.known_source_revisions)
    for source in context.sources:
        old = next(
            (
                item
                for item in revisions
                if (item.ref.kind, item.ref.version_id) == (source.ref.kind, source.ref.version_id)
            ),
            None,
        )
        if old is not None:
            if old.ref != source.ref or old.revision_fingerprint != source.revision_fingerprint:
                raise c.DialogueError("INVALID_EVENT")
        else:
            revisions.append(
                c.SourceRevisionReceipt(
                    ref=source.ref, revision_fingerprint=source.revision_fingerprint
                )
            )
    _available(state, context)
    if len(revisions) >= state.policy.max_events:
        raise c.DialogueError("CONTEXT_LIMIT")
    return _updated(state, known_source_revisions=tuple(revisions), **_context_fields(context))


def _known_callback(state, payload):
    """Return (reservation, is_current), or reject a forged/unknown binding."""
    delivery = isinstance(payload, (c.DeliveryStartedPayload, c.DeliveryCompletedPayload))
    value = payload.receipt if delivery else payload
    known = next(
        (item for item in state.known_requests if item.request_id == value.request_id), None
    )
    if known is None:
        raise c.DialogueError("INVALID_RESPONSE")
    if delivery:
        names = (
            "policy_version",
            "epoch",
            "context_id",
            "context_revision",
            "manifest_id",
            "manifest_version",
        )
        if (
            any(getattr(value, name) != getattr(known, name) for name in names)
            or value.response_id != uuid5(known.request_id, "response")
            or value.kind
            != ("started" if isinstance(payload, c.DeliveryStartedPayload) else "completed")
        ):
            raise c.DialogueError("INVALID_RESPONSE")
        slot = (
            state.ready_response
            if isinstance(payload, c.DeliveryStartedPayload)
            else state.active_response
        )
    else:
        if any(
            getattr(value, name) != getattr(known, name) for name in c.GENERATION_BINDING_FIELDS
        ):
            raise c.DialogueError("INVALID_RESPONSE")
        if isinstance(payload, c.ReadyPayload):
            response = payload.response
            if (
                any(
                    getattr(response, name) != getattr(known, name)
                    for name in c.GENERATION_BINDING_FIELDS
                )
                or response.effect_id != known.effect_id
                or response.response_id != uuid5(known.request_id, "response")
            ):
                raise c.DialogueError("INVALID_RESPONSE")
        slot = state.pending_effect
    current = (
        slot is not None and slot.request_id == known.request_id and known.epoch == state.epoch
    )
    return known, current


def _question_allowed(state, response, context):
    if response.outcome != "question":
        return True
    return not (
        response.topic_key in state.skipped_keys
        or response.question_key in context.asked_keys
        or any(
            receipt.response_id != response.response_id
            and (
                receipt.question_key == response.question_key
                or receipt.normalized_text == c.normalize_question(response.text)
            )
            for receipt in state.question_receipts
        )
    )


def _reserve(state, event, context, trigger, outcomes):
    try:
        _available(state, context)
    except c.DialogueError as error:
        if error.code == "CONTEXT_LIMIT":
            return _block(state, event, error.code, ordered=True)
        return _accept(
            state,
            state,
            event,
            result=c.ResultMetadata(code=error.code, disposition="rejected"),
        )
    if _at_capacity(state, known_requests=len(state.known_requests) + 1):
        return _block(state, event, "CONTEXT_LIMIT", ordered=True)
    request_id = uuid5(state.scope.session_id, f"generate:{event.event_id}")
    effect = c.GenerateEffect(
        effect_id=uuid5(request_id, "generate"),
        request_id=request_id,
        scope=state.scope,
        reservation_version=state.version + 1,
        policy_version=state.policy_version,
        epoch=state.epoch,
        context_id=context.id,
        context_revision=context.context_revision,
        manifest_id=context.manifest_id,
        manifest_version=context.manifest_version,
        silence_cycle=state.silence_cycle,
        trigger=trigger,
        allowed_outcomes=outcomes,
        dependency_refs=_dependency_refs(state, context),
    )
    after = _updated(
        state,
        pending_effect=effect,
        known_requests=(*state.known_requests, effect),
        status="generating",
        cycle_consumed=True if trigger == "auto" else state.cycle_consumed,
    )
    return _accept(
        state,
        after,
        event,
        (effect,),
        c.ResultMetadata(request_id=request_id),
    )


def _update_turn(state, turn_id, hint=None):
    old = next((turn for turn in state.turn_cycles if turn.human_turn_id == turn_id), None)
    if old is None:
        cycle = state.silence_cycle + 1
        turns = (
            *state.turn_cycles,
            c.HumanTurnRecord(
                human_turn_id=turn_id,
                assigned_cycle=cycle,
                semantic_hint=hint or "unknown",
            ),
        )
        return {
            "turn_cycles": turns,
            "current_human_turn_id": turn_id,
            "silence_cycle": cycle,
            "cycle_consumed": False,
            "auto_suspended": False,
            "semantic_hint": hint or "unknown",
        }
    changes = {}
    if hint is not None:
        changes["turn_cycles"] = tuple(
            _updated(turn, semantic_hint=hint) if turn.human_turn_id == turn_id else turn
            for turn in state.turn_cycles
        )
        if state.current_human_turn_id == turn_id:
            changes["semantic_hint"] = hint
    return changes


def _handle_callback(state, event, context, reservation):
    payload = event.payload
    if isinstance(payload, c.FailurePayload):
        return _accept(
            state,
            _updated(state, pending_effect=None, status="listening"),
            event,
            result=c.ResultMetadata(
                code=payload.error_code,
                disposition="accepted",
                request_id=reservation.request_id,
            ),
        )
    try:
        _available(state, context)
        if isinstance(payload, c.ReadyPayload):
            response = validate_response(payload.response, reservation, context)
        else:
            response = state.ready_response or state.active_response
            validate_response(response, reservation, context)
        if response.outcome == "question" and not (
            0 < len(c.normalize_question(response.text)) <= c.MAX_NORMALIZED_QUESTION_CHARS
        ):
            raise c.DialogueError("INVALID_RESPONSE")
        if not _question_allowed(state, response, context):
            raise c.DialogueError("INVALID_RESPONSE")
        if state.speaking or state.typing or state.mode != "light":
            raise c.DialogueError("INVALID_RESPONSE")
    except c.DialogueError as error:
        after, effects = _invalidate(state)
        return _accept(
            state,
            after,
            event,
            effects,
            c.ResultMetadata(code=error.code, disposition="rejected"),
        )
    metadata = c.ResultMetadata(request_id=response.request_id, response_id=response.response_id)
    if isinstance(payload, c.ReadyPayload):
        if response.outcome == "no_reply":
            return _accept(
                state,
                _updated(state, pending_effect=None, status="listening"),
                event,
                result=metadata,
            )
        after = _updated(state, pending_effect=None, ready_response=response, status="ready")
        return _accept(
            state,
            after,
            event,
            (c.DeliverEffect(effect_id=uuid5(response.request_id, "deliver"), response=response),),
            metadata,
        )
    if isinstance(payload, c.DeliveryStartedPayload):
        receipts = state.question_receipts
        if response.outcome == "question":
            if _at_capacity(state, question_receipts=len(receipts) + 1):
                return _block(state, event, "CONTEXT_LIMIT", ordered=True)
            receipts = (
                *receipts,
                c.QuestionReceipt(
                    request_id=response.request_id,
                    response_id=response.response_id,
                    epoch=response.epoch,
                    question_key=response.question_key,
                    topic_key=response.topic_key,
                    normalized_text=c.normalize_question(response.text),
                    delivery="started",
                    basis_refs=tuple(dict.fromkeys(q.ref for q in response.basis_quotes)),
                ),
            )
        after = _updated(
            state,
            ready_response=None,
            active_response=response,
            question_receipts=receipts,
            status="delivering",
        )
    else:
        # Only this active response can complete its own receipt.
        receipts = tuple(
            _updated(receipt, delivery="delivered")
            if receipt.response_id == response.response_id
            else receipt
            for receipt in state.question_receipts
        )
        after = _updated(
            state,
            active_response=None,
            question_receipts=receipts,
            status="listening",
        )
    return _accept(state, after, event, result=metadata)


def reduce_event(
    state: c.DialogueState,
    event: c.Event,
    policy: c.Policy,
    context: c.ContextSnapshot,
) -> c.Transition:
    """Apply one ordered fixture event; no calls, clocks, random reads or mutation."""
    try:
        state = c.DialogueState.model_validate(state)
        event = c.Event.model_validate(event)
    except (ValidationError, TypeError, ValueError):
        # A malformed State is a caller contract error; never manufacture authority.
        raise c.DialogueError("INVALID_EVENT") from None
    if event.scope != state.scope:
        return _reject(state)
    previous = next(
        (
            item
            for item in (*state.event_receipts, state.terminal_receipt)
            if item is not None and item.event_id == event.event_id
        ),
        None,
    )
    if previous is not None:
        if previous.digest != c.canonical_digest(event):
            return _reject(state, "EVENT_CONFLICT")
        return c.Transition(next_state=state, effects=(), result=previous.result)
    if state.status == "ended":
        return _reject(state)
    if state.status == "blocked" and event.kind != "end":
        return _reject(state)
    if event.seq != state.last_seq + 1 or event.time_ms < state.last_time_ms:
        return _block(state, event, "SEQUENCE_GAP", ordered=False)
    try:
        policy = c.Policy.model_validate(policy)
        if policy != state.policy or context.scope != state.scope:
            return _reject(state)
    except (ValidationError, TypeError, ValueError, AttributeError):
        return _reject(state)

    callback = isinstance(
        event.payload,
        (c.ReadyPayload, c.FailurePayload, c.DeliveryStartedPayload, c.DeliveryCompletedPayload),
    )
    reservation = None
    current_callback = False
    if callback:
        try:
            reservation, current_callback = _known_callback(state, event.payload)
        except c.DialogueError as error:
            return _reject(state, error.code)
    safety_stop = event.kind in {
        "speech_started",
        "typing_started",
        "pause",
        "end",
        "source_restricted",
    } or (isinstance(event.payload, c.SetModePayload) and event.payload.mode == "record_only")
    if (
        event.expected_version != state.version
        and not (safety_stop and event.expected_version < state.version)
        and not (callback and not current_callback)
    ):
        return _reject(state, "STALE_VERSION")
    explicit_replacement = (
        isinstance(event.payload, c.ReplaceSelectionPayload)
        and context.id == event.payload.context.id
        and context.context_revision == event.payload.context.context_revision
        and context.manifest_id == event.payload.context.manifest_id
        and context.manifest_version == event.payload.context.manifest_version
    )
    if (
        event.kind != "user_message_committed"
        and not explicit_replacement
        and not _same_context(state, context)
    ):
        return _reject(state)
    if event.kind == "end":
        after, effects = _invalidate(state)
        after = _updated(
            after,
            status="ended",
            speaking=False,
            typing=False,
            active_speech_turn_id=None,
            silence_since_ms=None,
        )
        return _accept(state, after, event, effects, terminal=True)
    if _at_capacity(state, extra_events=1):
        return _block(state, event, "CONTEXT_LIMIT", ordered=True)
    if callback:
        if not current_callback:
            return _ignored(state, event)
        return _handle_callback(state, event, context, reservation)

    payload = event.payload
    if isinstance(payload, c.StartPayload):
        if state.status != "idle":
            return _reject(state)
        return _accept(state, _updated(state, status="listening"), event)
    if isinstance(payload, c.PausePayload):
        if state.status in {"idle", "paused"}:
            return _reject(state)
        after, effects = _invalidate(state)
        return _accept(state, _updated(after, status="paused", auto_suspended=True), event, effects)
    if isinstance(payload, c.ResumePayload):
        if state.status != "paused":
            return _reject(state)
        return _accept(state, _updated(state, status="listening"), event)
    if isinstance(payload, c.SetModePayload):
        if payload.mode == state.mode:
            return _ignored(state, event)
        after, effects = _invalidate(state, mode=payload.mode)
        return _accept(state, after, event, effects)
    if isinstance(payload, c.SourceRestrictedPayload):
        relevant = payload.ref in state.context_source_refs or any(
            payload.ref in known.dependency_refs for known in state.known_requests
        )
        if not relevant or payload.ref in state.restricted_refs:
            return _ignored(state, event)
        if _at_capacity(state, restricted_refs=len(state.restricted_refs) + 1):
            return _block(state, event, "CONTEXT_LIMIT", ordered=True)
        after, effects = _invalidate(state, restricted_refs=(*state.restricted_refs, payload.ref))
        return _accept(state, after, event, effects)
    if isinstance(payload, c.ReplaceSelectionPayload):
        try:
            after = _adopt_context(state, payload.context, replace=True)
        except c.DialogueError as error:
            if error.code == "CONTEXT_LIMIT":
                return _block(state, event, error.code, ordered=True)
            return _reject(state, error.code)
        after, effects = _invalidate(after)
        return _accept(state, after, event, effects)
    if isinstance(payload, (c.SkipTopicPayload, c.UnskipTopicPayload)):
        keys = state.skipped_keys
        if isinstance(payload, c.SkipTopicPayload):
            if payload.topic_key in keys:
                return _ignored(state, event)
            if _at_capacity(state, skipped_keys=len(keys) + 1):
                return _block(state, event, "CONTEXT_LIMIT", ordered=True)
            after, effects = _invalidate(state, skipped_keys=(*keys, payload.topic_key))
        else:
            if payload.topic_key not in keys:
                return _ignored(state, event)
            after, effects = _invalidate(
                state, skipped_keys=tuple(key for key in keys if key != payload.topic_key)
            )
        return _accept(state, after, event, effects)
    if isinstance(payload, c.SilenceElapsedPayload):
        if (
            state.status != "listening"
            or state.mode != "light"
            or state.speaking
            or state.typing
            or state.current_human_turn_id != payload.human_turn_id
            or state.silence_cycle != payload.silence_cycle
            or state.silence_since_ms is None
            or state.cycle_consumed
            or state.auto_suspended
        ):
            return _ignored(state, event)
        complete = state.semantic_hint == "complete"
        threshold = policy.complete_pause_ms if complete else policy.uncertain_pause_ms
        if event.time_ms - state.silence_since_ms < threshold:
            return _ignored(state, event)
        outcomes = ("ack", "question", "no_reply") if complete else ("ack", "no_reply")
        return _reserve(state, event, context, "auto", outcomes)
    if isinstance(payload, c.RequestResponsePayload):
        if state.status != "listening" or state.mode != "light" or state.speaking or state.typing:
            return _reject(state)
        return _reserve(state, event, context, "manual", ("question", "no_reply"))
    if state.status == "idle":
        return _reject(state)
    if isinstance(payload, c.SpeechStartedPayload):
        if state.speaking:
            if state.active_speech_turn_id == payload.human_turn_id:
                return _ignored(state, event)
            return _reject(state)
        turns = _update_turn(state, payload.human_turn_id)
        if _at_capacity(state, turn_cycles=len(turns.get("turn_cycles", state.turn_cycles))):
            return _block(state, event, "CONTEXT_LIMIT", ordered=True)
        after, effects = _invalidate(
            state,
            speaking=True,
            active_speech_turn_id=payload.human_turn_id,
            silence_since_ms=None,
            **turns,
        )
        return _accept(state, after, event, effects)
    if isinstance(payload, c.SpeechEndedPayload):
        if not state.speaking or payload.human_turn_id != state.active_speech_turn_id:
            return _reject(state)
        after = _updated(
            state,
            speaking=False,
            active_speech_turn_id=None,
            silence_since_ms=None if state.typing else event.time_ms,
            **_update_turn(state, payload.human_turn_id, payload.semantic_hint),
        )
        return _accept(state, after, event)
    if isinstance(payload, c.TypingStartedPayload):
        if state.typing:
            return _ignored(state, event)
        after, effects = _invalidate(state, typing=True, silence_since_ms=None)
        return _accept(state, after, event, effects)
    if isinstance(payload, c.TypingEndedPayload):
        if not state.typing:
            return _reject(state)
        after = _updated(
            state,
            typing=False,
            silence_since_ms=None if state.speaking else event.time_ms,
        )
        return _accept(state, after, event)
    if isinstance(payload, c.UserMessageCommittedPayload):
        ref = payload.message_ref
        scope = ref.source_scope
        known_turn = any(turn.human_turn_id == payload.human_turn_id for turn in state.turn_cycles)
        if (
            ref.kind != "message"
            or scope.origin_session_id != state.scope.session_id
            or scope.origin_interview_id != state.scope.interview_id
            or ref in state.committed_refs
            or (ref.origin == "user_text" and known_turn)
            or (ref.origin == "voice_final" and not known_turn)
        ):
            return _reject(state)
        try:
            adopted = _adopt_context(state, context, committed_ref=ref)
        except c.DialogueError as error:
            if error.code == "CONTEXT_LIMIT":
                return _block(state, event, error.code, ordered=True)
            return _reject(state, error.code)
        turns = _update_turn(state, payload.human_turn_id, payload.semantic_hint)
        if _at_capacity(
            state,
            committed_refs=len(state.committed_refs) + 1,
            turn_cycles=len(turns.get("turn_cycles", state.turn_cycles)),
        ):
            return _block(state, event, "CONTEXT_LIMIT", ordered=True)
        changes = {**turns, "committed_refs": (*state.committed_refs, ref)}
        if not known_turn or state.current_human_turn_id == payload.human_turn_id:
            changes["silence_since_ms"] = None if state.speaking or state.typing else event.time_ms
        # A late previous-turn commit changes dependencies, never the current clock/hint.
        after, effects = _invalidate(adopted, **changes)
        return _accept(state, after, event, effects)
    return _reject(state)
