"""Ordered synthetic event reducer tests; no application, device or storage adapters."""

from uuid import uuid5

import pytest
from pydantic import ValidationError
from test_dialogue_contracts import (
    event,
    make_context,
    make_manifest,
    make_policy,
    make_scope,
    make_source,
    step,
    uid,
)

from app.dialogue import contracts as dto
from app.dialogue.controller import create_state, reduce_event
from app.dialogue.mock import DeterministicDialogueMock
from app.dialogue.provider import sourced_question
from app.dialogue.runner import envelope_callback, run_effect


def _history_item(response, *, sequence=1):
    return dto.HistoryItem(
        sequence=sequence,
        role="assistant",
        text=response.text,
        delivery="delivered",
        response_id=response.response_id,
    )


def responding_effects(transition):
    return tuple(effect for effect in transition.effects if effect.kind in {"generate", "deliver"})


def started(*, policy=None, context=None):
    policy = policy or make_policy()
    context = context or make_context(policy=policy)
    state = create_state(context.scope, policy, context)
    transition = step(state, dto.StartPayload(), policy, context)
    assert transition.result.code == "OK"
    return transition.next_state, policy, context


def quiet_turn(*, hint="complete", policy=None, context=None, name="turn"):
    state, policy, context = started(policy=policy, context=context)
    turn_id = uid(name)
    state = step(
        state,
        dto.SpeechStartedPayload(human_turn_id=turn_id),
        policy,
        context,
        time_ms=2,
    ).next_state
    transition = step(
        state,
        dto.SpeechEndedPayload(human_turn_id=turn_id, semantic_hint=hint),
        policy,
        context,
        time_ms=10,
    )
    assert transition.result.code == "OK"
    return transition.next_state, policy, context


def tick(state, policy, context, *, time_ms):
    return step(
        state,
        dto.SilenceElapsedPayload(
            human_turn_id=state.current_human_turn_id,
            silence_cycle=state.silence_cycle,
        ),
        policy,
        context,
        time_ms=time_ms,
    )


def generating(*, hint="complete", policy=None, context=None):
    state, policy, context = quiet_turn(hint=hint, policy=policy, context=context)
    delay = policy.complete_pause_ms if hint == "complete" else policy.uncertain_pause_ms
    transition = tick(state, policy, context, time_ms=10 + delay)
    assert transition.result.code == "OK"
    effect = next(item for item in transition.effects if item.kind == "generate")
    return transition.next_state, policy, context, effect


def ready(*, provider=None):
    state, policy, context, effect = generating()
    payload = run_effect(effect, context, provider or DeterministicDialogueMock())
    transition = reduce_event(state, envelope_callback(state, payload, 111), policy, context)
    assert transition.result.code == "OK"
    assert transition.next_state.status == "ready"
    return transition.next_state, policy, context, payload.response


def receipt(response, kind):
    names = (
        "request_id",
        "response_id",
        "policy_version",
        "epoch",
        "context_id",
        "context_revision",
        "manifest_id",
        "manifest_version",
    )
    return dto.DeliveryReceipt(**{name: getattr(response, name) for name in names}, kind=kind)


def begin_delivery(state, policy, context, response):
    return step(
        state,
        dto.DeliveryStartedPayload(receipt=receipt(response, "started")),
        policy,
        context,
    )


def _source_removed_but_history_retained():
    state, policy, context, response = ready(
        provider=DeterministicDialogueMock(basis_kind="sourced")
    )
    original_ref = context.source_refs[0]
    state = begin_delivery(state, policy, context, response).next_state
    state = step(
        state,
        dto.DeliveryCompletedPayload(receipt=receipt(response, "completed")),
        policy,
        context,
    ).next_state
    history = (_history_item(response),)
    replacement = make_context(
        sources=(),
        history=history,
        manifest=make_manifest(context.scope, version=2),
        context_revision=2,
    )
    changed = step(state, dto.ReplaceSelectionPayload(context=replacement), policy, replacement)
    assert changed.result.code == "OK"
    assert original_ref not in replacement.source_refs
    return changed.next_state, policy, replacement, original_ref


@pytest.mark.parametrize("depth", [1, 2], ids=("direct-history", "transitive-history"))
def test_ir01_c40_c57_restrict_after_selection_removal_blocks_ai_history_before_hash(
    depth, monkeypatch
):
    state, policy, context, original_ref = _source_removed_but_history_retained()
    if depth == 2:
        generated = step(state, dto.RequestResponsePayload(), policy, context)
        effect = generated.next_state.pending_effect
        assert original_ref in effect.dependency_refs
        assert context.source_refs == ()
        payload = run_effect(
            effect,
            context,
            DeterministicDialogueMock(question_key="neutral-2", text=dto.NEUTRAL_QUESTIONS[1]),
        )
        assert isinstance(payload, dto.ReadyPayload)
        result = reduce_event(
            generated.next_state,
            envelope_callback(generated.next_state, payload, generated.next_state.last_time_ms + 1),
            policy,
            context,
        )
        assert result.result.code == "OK"
        state = begin_delivery(result.next_state, policy, context, payload.response).next_state
        state = step(
            state,
            dto.DeliveryCompletedPayload(receipt=receipt(payload.response, "completed")),
            policy,
            context,
        ).next_state
        replacement = make_context(
            sources=(),
            history=(_history_item(payload.response),),
            manifest=make_manifest(context.scope, version=3),
            context_revision=3,
        )
        result = step(state, dto.ReplaceSelectionPayload(context=replacement), policy, replacement)
        assert result.result.code == "OK"
        state, context = result.next_state, replacement

    restricted = step(state, dto.SourceRestrictedPayload(ref=original_ref), policy, context)
    assert restricted.result.code == "OK"
    assert restricted.next_state.restricted_refs == (original_ref,)
    original_digest = dto.canonical_digest

    def forbid_context_body_hash(value):
        assert not isinstance(value, dto.ContextSnapshot), "Restricted AI text must remain unread"
        return original_digest(value)

    with monkeypatch.context() as guard:
        guard.setattr(dto, "canonical_digest", forbid_context_body_hash)
        refused = step(restricted.next_state, dto.RequestResponsePayload(), policy, context)
        assert refused.result.code == "SOURCE_UNAVAILABLE"
        assert refused.effects == ()
        assert refused.next_state.pending_effect is None
        assert refused.next_state.known_requests == restricted.next_state.known_requests
        stopped = step(refused.next_state, dto.TypingStartedPayload(), policy, context)
        assert stopped.result.code == "OK"
        assert stopped.next_state.typing is True
        assert responding_effects(stopped) == ()

    clean = make_context(
        sources=(),
        history=(),
        manifest=make_manifest(context.scope, version=context.manifest_version + 1),
        context_revision=context.context_revision + 1,
    )
    cleaned = step(stopped.next_state, dto.ReplaceSelectionPayload(context=clean), policy, clean)
    assert cleaned.result.code == "OK"
    resumed = step(cleaned.next_state, dto.TypingEndedPayload(), policy, clean)
    generated = step(resumed.next_state, dto.RequestResponsePayload(), policy, clean)
    assert generated.result.code == "OK"
    assert generated.next_state.pending_effect.dependency_refs == ()
    assert generated.next_state.restricted_refs == (original_ref,)
    fresh = run_effect(
        generated.next_state.pending_effect,
        clean,
        DeterministicDialogueMock(question_key="post-clean", text=dto.NEUTRAL_QUESTIONS[2]),
    )
    result = reduce_event(
        generated.next_state,
        envelope_callback(generated.next_state, fresh, generated.next_state.last_time_ms + 1),
        policy,
        clean,
    )
    assert result.result.code == "OK"
    retained = make_context(
        sources=(),
        history=(_history_item(fresh.response),),
        manifest=make_manifest(clean.scope, version=clean.manifest_version + 1),
        context_revision=clean.context_revision + 1,
    )
    updated = step(
        result.next_state, dto.ReplaceSelectionPayload(context=retained), policy, retained
    )
    assert updated.result.code == "OK"
    next_request = step(updated.next_state, dto.RequestResponsePayload(), policy, retained)
    assert next_request.result.code == "OK"
    assert next_request.next_state.pending_effect.dependency_refs == ()


@pytest.mark.parametrize(
    "invalid", ["missing-raw", "unexplained-extra", "duplicate", "cross-scope"]
)
def test_ir01_dependency_metadata_cannot_add_readable_sources_or_bypass_runner_scope(invalid):
    source = make_source()
    context = make_context(sources=(source,))
    if invalid == "cross-scope":
        context = make_context(
            sources=(source,),
            history=(
                dto.HistoryItem(sequence=1, role="user", ref=source.ref, text=source.text),
                dto.HistoryItem(
                    sequence=2,
                    role="assistant",
                    text="合成中性历史。",
                    response_id=uid("fixture-ai-history"),
                    delivery="delivered",
                ),
            ),
        )
    _, _, context, effect = generating(context=context)
    if invalid == "missing-raw":
        dependencies = ()
    elif invalid == "duplicate":
        dependencies = (source.ref, source.ref)
    else:
        extra_scope = (
            make_scope(actor_user_id=uid("other-fixture-owner"))
            if invalid == "cross-scope"
            else context.scope
        )
        extra = make_source("dependency-only", scope=extra_scope, kind="document_version")
        dependencies = (source.ref, extra.ref)
    changed = dto.GenerateEffect(**(effect.model_dump() | {"dependency_refs": dependencies}))
    provider = DeterministicDialogueMock()
    result = run_effect(changed, context, provider)
    assert isinstance(result, dto.FailurePayload)
    assert result.error_code == "INVALID_EVENT"
    assert provider.calls == 0


@pytest.mark.parametrize("phase", ["generating", "ready", "delivering"])
def test_ir01_c40_c57_removed_raw_source_still_cancels_dependent_history_output(phase):
    state, policy, context, original_ref = _source_removed_but_history_retained()
    generated = step(state, dto.RequestResponsePayload(), policy, context)
    effect = generated.next_state.pending_effect
    assert effect.dependency_refs == (original_ref,)
    assert context.source_refs == ()
    provider = DeterministicDialogueMock(question_key="neutral-2", text=dto.NEUTRAL_QUESTIONS[1])
    payload = run_effect(effect, context, provider)
    assert isinstance(payload, dto.ReadyPayload)
    state = generated.next_state
    if phase != "generating":
        state = reduce_event(
            state, envelope_callback(state, payload, state.last_time_ms + 1), policy, context
        ).next_state
    if phase == "delivering":
        state = begin_delivery(state, policy, context, payload.response).next_state
        assert state.question_receipts[-1].delivery == "started"
    restricted = step(state, dto.SourceRestrictedPayload(ref=original_ref), policy, context)
    assert restricted.result.code == "OK"
    assert restricted.next_state.pending_effect is None
    assert restricted.next_state.ready_response is None
    assert restricted.next_state.active_response is None
    expected_effect = "cancel_generation" if phase == "generating" else "stop_playback"
    assert any(item.kind == expected_effect for item in restricted.effects)
    if phase == "delivering":
        assert restricted.next_state.question_receipts[-1].delivery == "interrupted"
    refused = step(restricted.next_state, dto.RequestResponsePayload(), policy, context)
    assert refused.result.code == "SOURCE_UNAVAILABLE"
    assert refused.effects == ()
    assert provider.calls == 1


@pytest.mark.parametrize(
    "normalized_length,accepted",
    [(2000, True), (2001, False), (2100, False)],
    ids=("normalized-boundary", "one-past-boundary", "ligature-expansion"),
)
def test_ir03_c55_normalized_capacity_checked_before_deliver(normalized_length, accepted):
    overhead = len(dto.normalize_question(sourced_question("x"))) - 1
    text = "\ufb03" * 600 + "a" * (normalized_length - overhead - 1800)
    source = make_source("unicode-capacity", text=text)
    context = make_context(sources=(source,))
    state, policy, context = started(context=context)
    generated = step(state, dto.RequestResponsePayload(), policy, context)
    payload = run_effect(
        generated.next_state.pending_effect,
        context,
        DeterministicDialogueMock(basis_kind="sourced"),
    )
    assert isinstance(payload, dto.ReadyPayload)
    assert len(payload.response.text) <= 2000
    assert len(dto.normalize_question(payload.response.text)) == normalized_length
    result = reduce_event(
        generated.next_state,
        envelope_callback(generated.next_state, payload, generated.next_state.last_time_ms + 1),
        policy,
        context,
    )
    if not accepted:
        assert result.result.code == "INVALID_RESPONSE"
        assert responding_effects(result) == ()
        assert result.next_state.status == "listening"
        assert result.next_state.ready_response is None
        assert result.next_state.question_receipts == ()
        late_delivery = begin_delivery(result.next_state, policy, context, payload.response)
        assert late_delivery.result.disposition == "ignored"
        assert late_delivery.effects == ()
        assert late_delivery.next_state.question_receipts == ()
    else:
        assert result.result.code == "OK"
        assert any(item.kind == "deliver" for item in result.effects)
        assert result.next_state.ready_response.text == payload.response.text
        delivery = begin_delivery(result.next_state, policy, context, payload.response)
        assert delivery.result.code == "OK"
        assert len(delivery.next_state.question_receipts[-1].normalized_text) == normalized_length
        assert delivery.next_state.question_receipts[-1].delivery == "started"
        completed = step(
            delivery.next_state,
            dto.DeliveryCompletedPayload(receipt=receipt(payload.response, "completed")),
            policy,
            context,
        )
        assert completed.result.code == "OK"
        assert completed.next_state.question_receipts[-1].delivery == "delivered"


def test_c52_late_a_commit_cannot_refill_already_consumed_b_allowance():
    empty = make_context(sources=())
    state, policy, _ = quiet_turn(context=empty, name="spent-A")
    state = step(
        state,
        dto.SpeechStartedPayload(human_turn_id=uid("spent-B")),
        policy,
        empty,
        time_ms=20,
    ).next_state
    state = step(
        state,
        dto.SpeechEndedPayload(human_turn_id=uid("spent-B"), semantic_hint="incomplete"),
        policy,
        empty,
        time_ms=30,
    ).next_state
    generated = tick(state, policy, empty, time_ms=330)
    provider = DeterministicDialogueMock(outcome="no_reply")
    payload = run_effect(generated.next_state.pending_effect, empty, provider)
    completed = reduce_event(
        generated.next_state, envelope_callback(generated.next_state, payload, 331), policy, empty
    )
    assert completed.next_state.status == "listening"
    assert completed.next_state.cycle_consumed is True
    source = make_source("spent-a-final", origin="voice_final")
    rebuilt = make_context(sources=(source,), context_revision=2)
    late = step(
        completed.next_state,
        dto.UserMessageCommittedPayload(
            human_turn_id=uid("spent-A"), message_ref=source.ref, semantic_hint="complete"
        ),
        policy,
        rebuilt,
        time_ms=340,
    )
    assert late.result.code == "OK"
    assert late.next_state.current_human_turn_id == uid("spent-B")
    assert late.next_state.semantic_hint == "incomplete"
    assert late.next_state.silence_cycle == 2
    assert late.next_state.silence_since_ms == 30
    assert late.next_state.cycle_consumed is True
    after_silence = tick(late.next_state, policy, rebuilt, time_ms=1000)
    assert after_silence.effects == ()
    assert after_silence.next_state.known_requests == completed.next_state.known_requests
    assert provider.calls == 1


@pytest.mark.parametrize("callback", ["ready", "failed", "delivery"])
@pytest.mark.parametrize("phase", ["ready", "delivering"])
def test_c54_old_callbacks_preserve_new_ready_or_active_response_and_receipt(callback, phase):
    state, policy, context, old_effect = generating()
    old_payload = run_effect(old_effect, context, DeterministicDialogueMock())
    state = step(state, dto.PausePayload(), policy, context).next_state
    state = step(state, dto.ResumePayload(), policy, context).next_state
    state = step(state, dto.RequestResponsePayload(), policy, context).next_state
    new_payload = run_effect(state.pending_effect, context, DeterministicDialogueMock())
    ready_result = reduce_event(
        state, envelope_callback(state, new_payload, state.last_time_ms + 1), policy, context
    )
    assert ready_result.result.code == "OK"
    state = ready_result.next_state
    if phase == "delivering":
        state = begin_delivery(state, policy, context, new_payload.response).next_state
        assert state.active_response == new_payload.response
        assert state.question_receipts[-1].delivery == "started"
    if callback == "ready":
        old = old_payload
    elif callback == "failed":
        old = dto.FailurePayload(**dto.generation_binding(old_effect), error_code="PROVIDER_FAILED")
    else:
        old = dto.DeliveryCompletedPayload(receipt=receipt(old_payload.response, "completed"))
    ignored = step(state, old, policy, context, expected_version=0)
    assert ignored.result.disposition == "ignored"
    assert ignored.effects == ()
    assert ignored.next_state.status == phase
    assert ignored.next_state.ready_response == state.ready_response
    assert ignored.next_state.active_response == state.active_response
    assert ignored.next_state.question_receipts == state.question_receipts
    assert ignored.next_state.known_requests == state.known_requests
    assert ignored.next_state.epoch == state.epoch
    assert ignored.next_state.version == state.version + 1
    state = ignored.next_state
    if phase == "ready":
        state = begin_delivery(state, policy, context, new_payload.response).next_state
    completed = step(
        state,
        dto.DeliveryCompletedPayload(receipt=receipt(new_payload.response, "completed")),
        policy,
        context,
    )
    assert completed.result.code == "OK"
    assert completed.next_state.status == "listening"
    assert completed.next_state.active_response is None
    assert (
        completed.next_state.question_receipts[-1].response_id == new_payload.response.response_id
    )
    assert completed.next_state.question_receipts[-1].delivery == "delivered"


def test_c02_reducer_keeps_state_context_and_event_immutable():
    policy, context = make_policy(), make_context()
    state = create_state(context.scope, policy, context)
    command = event(state, dto.StartPayload())
    before = state.model_dump_json(), context.model_dump_json(), command.model_dump_json()
    result = reduce_event(state, command, policy, context)
    assert before == (state.model_dump_json(), context.model_dump_json(), command.model_dump_json())
    assert state.status == "idle"
    assert result.next_state.status == "listening"
    with pytest.raises(ValidationError):
        result.next_state.version = 99


def test_c04_start_light_listens_without_automatic_opening():
    state, _, _ = started()
    assert state.status == "listening"
    assert state.mode == "light"
    assert state.pending_effect is None
    assert state.current_human_turn_id is None
    assert state.known_requests == ()


@pytest.mark.parametrize("activity", ["speech", "typing", "both"])
def test_c05_c06_c07_active_input_blocks_manual_and_automatic_output(activity):
    state, policy, context = quiet_turn()
    if activity in {"speech", "both"}:
        state = step(
            state,
            dto.SpeechStartedPayload(human_turn_id=uid("next-turn")),
            policy,
            context,
        ).next_state
    if activity in {"typing", "both"}:
        state = step(state, dto.TypingStartedPayload(), policy, context).next_state
    manual = step(state, dto.RequestResponsePayload(), policy, context)
    assert responding_effects(manual) == ()
    assert manual.next_state.pending_effect is None
    automatic = tick(manual.next_state, policy, context, time_ms=1000)
    assert responding_effects(automatic) == ()
    assert automatic.next_state.silence_since_ms is None
    if activity == "both":
        ended = step(automatic.next_state, dto.TypingEndedPayload(), policy, context)
        assert ended.next_state.speaking is True
        assert ended.next_state.silence_since_ms is None
        assert (
            responding_effects(
                step(
                    ended.next_state,
                    dto.RequestResponsePayload(),
                    policy,
                    context,
                )
            )
            == ()
        )


def test_c08_c09_complete_threshold_reserves_once_and_preserves_silence_origin():
    state, policy, context = quiet_turn()
    early = tick(state, policy, context, time_ms=109)
    assert responding_effects(early) == ()
    assert early.next_state.silence_since_ms == 10
    due = tick(early.next_state, policy, context, time_ms=110)
    effect = next(effect for effect in due.effects if effect.kind == "generate")
    assert effect.allowed_outcomes == ("ack", "question", "no_reply")
    assert due.next_state.cycle_consumed is True
    assert due.next_state.pending_effect == effect
    assert due.next_state.known_requests == (effect,)
    repeat = tick(due.next_state, policy, context, time_ms=1000)
    assert responding_effects(repeat) == ()
    assert repeat.next_state.silence_since_ms == 10


@pytest.mark.parametrize("hint", ["incomplete", "unknown"])
def test_c10_incomplete_and_unknown_use_longer_wait_and_neutral_outcomes(hint):
    state, policy, context = quiet_turn(hint=hint)
    early = tick(state, policy, context, time_ms=110)
    assert responding_effects(early) == ()
    due = tick(early.next_state, policy, context, time_ms=310)
    effect = next(effect for effect in due.effects if effect.kind == "generate")
    assert effect.allowed_outcomes == ("ack", "no_reply")
    assert "question" not in effect.allowed_outcomes


def test_c11_ai_delivery_and_later_ticks_do_not_refill_automatic_allowance():
    state, policy, context, response = ready()
    state = begin_delivery(state, policy, context, response).next_state
    state = step(
        state,
        dto.DeliveryCompletedPayload(receipt=receipt(response, "completed")),
        policy,
        context,
    ).next_state
    assert state.status == "listening"
    assert state.cycle_consumed is True
    assert state.silence_since_ms == 10
    transition = tick(state, policy, context, time_ms=2000)
    assert responding_effects(transition) == ()
    assert len(transition.next_state.known_requests) == 1


def test_c12_c52_speech_start_end_and_final_commit_share_one_cycle():
    scope, policy = make_scope(), make_policy()
    initial = make_context(sources=(), policy=policy)
    state, _, _ = quiet_turn(policy=policy, context=initial)
    source = make_source("voice", origin="voice_final")
    rebuilt = make_context(sources=(source,), context_revision=2, policy=policy)
    transition = step(
        state,
        dto.UserMessageCommittedPayload(
            human_turn_id=uid("turn"),
            message_ref=source.ref,
            semantic_hint="complete",
        ),
        policy,
        rebuilt,
    )
    assert transition.result.code == "OK"
    assert transition.next_state.silence_cycle == 1
    assert len(transition.next_state.turn_cycles) == 1
    assert transition.next_state.committed_refs == (source.ref,)
    assert transition.next_state.scope == scope
    duplicate = step(
        transition.next_state,
        dto.UserMessageCommittedPayload(
            human_turn_id=uid("new-id-cannot-recommit"),
            message_ref=source.ref,
            semantic_hint="complete",
        ),
        policy,
        rebuilt,
    )
    assert duplicate.result.code == "INVALID_EVENT"
    assert duplicate.next_state == transition.next_state


def test_c12_c13_text_commit_cannot_reuse_an_existing_human_turn_id():
    state, policy, context = quiet_turn()
    source = make_source("text-cannot-reuse-turn")
    rebuilt = make_context(sources=(*context.sources, source), context_revision=2)
    refused = step(
        state,
        dto.UserMessageCommittedPayload(
            human_turn_id=state.current_human_turn_id,
            message_ref=source.ref,
            semantic_hint="complete",
        ),
        policy,
        rebuilt,
    )
    assert refused.result.code == "INVALID_EVENT"
    assert refused.next_state == state
    assert refused.next_state.committed_refs == ()
    assert responding_effects(refused) == ()


def test_c13_typing_end_does_not_create_turn_or_refill_cycle():
    state, policy, context, _ = generating()
    state = step(state, dto.TypingStartedPayload(), policy, context).next_state
    old_turn, old_cycle = state.current_human_turn_id, state.silence_cycle
    ended = step(state, dto.TypingEndedPayload(), policy, context)
    assert ended.next_state.current_human_turn_id == old_turn
    assert ended.next_state.silence_cycle == old_cycle
    assert ended.next_state.cycle_consumed is True
    assert ended.next_state.committed_refs == ()
    new = step(
        ended.next_state,
        dto.SpeechStartedPayload(human_turn_id=uid("new-turn")),
        policy,
        context,
    )
    assert new.next_state.silence_cycle == old_cycle + 1
    assert new.next_state.cycle_consumed is False


@pytest.mark.parametrize("outcome", ["no_reply", "failure"])
def test_c14_c15_c45_no_reply_or_failure_cannot_automatically_retry(outcome):
    state, policy, context, effect = generating()
    provider = DeterministicDialogueMock(
        outcome="no_reply",
        script=(RuntimeError("合成禁止泄露正文"),) if outcome == "failure" else None,
    )
    payload = run_effect(effect, context, provider)
    transition = reduce_event(state, envelope_callback(state, payload, 111), policy, context)
    assert provider.calls == 1
    assert responding_effects(transition) == ()
    assert transition.next_state.pending_effect is None
    assert transition.next_state.cycle_consumed is True
    assert "合成禁止泄露正文" not in transition.model_dump_json()
    again = tick(transition.next_state, policy, context, time_ms=1000)
    assert responding_effects(again) == ()
    assert provider.calls == 1


def test_c15_cancelled_generation_keeps_silence_allowance_consumed():
    state, policy, context, _ = generating()
    paused = step(state, dto.PausePayload(), policy, context)
    assert "cancel_generation" in tuple(effect.kind for effect in paused.effects)
    resumed = step(paused.next_state, dto.ResumePayload(), policy, context)
    assert resumed.next_state.cycle_consumed is True
    assert responding_effects(tick(resumed.next_state, policy, context, time_ms=1000)) == ()


def test_c16_manual_requests_work_without_source_and_do_not_manufacture_answers():
    context = make_context(sources=(), history=())
    state, policy, context = started(context=context)
    first = step(state, dto.RequestResponsePayload(), policy, context)
    effect = next(item for item in first.effects if item.kind == "generate")
    assert effect.trigger == "manual"
    assert effect.allowed_outcomes == ("question", "no_reply")
    assert first.next_state.committed_refs == ()
    assert context.source_refs == ()
    payload = run_effect(effect, context, DeterministicDialogueMock(outcome="no_reply"))
    state = reduce_event(
        first.next_state,
        envelope_callback(first.next_state, payload, 3),
        policy,
        context,
    ).next_state
    second = step(state, dto.RequestResponsePayload(), policy, context)
    assert len(responding_effects(second)) == 1
    assert second.next_state.committed_refs == ()
    assert second.next_state.silence_cycle == 0


def test_c17_replay_returns_metadata_without_reexecuting_stub_or_effect():
    state, policy, context = quiet_turn()
    command = event(
        state,
        dto.SilenceElapsedPayload(
            human_turn_id=state.current_human_turn_id,
            silence_cycle=state.silence_cycle,
        ),
        time_ms=110,
    )
    first = reduce_event(state, command, policy, context)
    provider = DeterministicDialogueMock()
    effect = next(item for item in first.effects if item.kind == "generate")
    run_effect(effect, context, provider)
    replay = reduce_event(first.next_state, command, policy, context)
    assert replay.effects == ()
    assert replay.next_state == first.next_state
    assert replay.result.request_id == first.result.request_id
    assert replay.result == first.result
    assert provider.calls == 1


def test_c18_same_event_id_with_changed_payload_rejected_without_body():
    state, policy, context = started()
    command = event(state, dto.SkipTopicPayload(topic_key="synthetic-topic"))
    accepted = reduce_event(state, command, policy, context)
    conflict = dto.Event(
        **(
            command.model_dump()
            | {
                "payload": dto.SkipTopicPayload(topic_key="合成禁止泄露正文"),
            }
        )
    )
    rejected = reduce_event(accepted.next_state, conflict, policy, context)
    assert rejected.result.code == "EVENT_CONFLICT"
    assert rejected.next_state == accepted.next_state
    assert responding_effects(rejected) == ()
    assert "合成禁止泄露正文" not in rejected.result.model_dump_json()


@pytest.mark.parametrize("changes", [{"seq": 99}, {"seq": 1}, {"time_ms": 1}])
def test_c19_sequence_or_time_regression_blocks_and_cancels(changes):
    state, policy, context, _ = generating()
    command = event(state, dto.RequestResponsePayload(), **changes)
    transition = reduce_event(state, command, policy, context)
    assert transition.result.code == "SEQUENCE_GAP"
    assert transition.next_state.status == "blocked"
    assert transition.next_state.pending_effect is None
    assert "cancel_generation" in tuple(effect.kind for effect in transition.effects)
    assert responding_effects(transition) == ()


def test_c20_stale_version_cannot_reserve_another_generation():
    state, policy, context, _ = generating()
    transition = step(
        state,
        dto.RequestResponsePayload(),
        policy,
        context,
        expected_version=state.version - 1,
    )
    assert transition.result.code == "STALE_VERSION"
    assert transition.next_state == state
    assert len(state.known_requests) == 1
    assert responding_effects(transition) == ()


def test_c21_record_only_accepts_input_but_never_generates_or_delivers():
    policy = make_policy(mode="record_only")
    state, policy, context = quiet_turn(policy=policy)
    assert state.mode == "record_only"
    assert responding_effects(tick(state, policy, context, time_ms=1000)) == ()
    assert responding_effects(step(state, dto.RequestResponsePayload(), policy, context)) == ()
    typing = step(state, dto.TypingStartedPayload(), policy, context)
    assert typing.next_state.typing is True


def test_c22_pause_stops_playback_resume_does_not_republish():
    state, policy, context, response = ready()
    state = begin_delivery(state, policy, context, response).next_state
    paused = step(state, dto.PausePayload(), policy, context)
    assert paused.next_state.status == "paused"
    assert "stop_playback" in tuple(effect.kind for effect in paused.effects)
    assert paused.next_state.active_response is None
    resumed = step(paused.next_state, dto.ResumePayload(), policy, context)
    assert resumed.next_state.status == "listening"
    assert responding_effects(resumed) == ()
    assert resumed.next_state.cycle_consumed is True


def test_c23_end_is_terminal_with_replay_metadata_only():
    state, policy, context, _ = generating()
    command = event(state, dto.EndPayload())
    ended = reduce_event(state, command, policy, context)
    assert ended.next_state.status == "ended"
    assert responding_effects(ended) == ()
    replay = reduce_event(ended.next_state, command, policy, context)
    assert replay.effects == ()
    assert replay.result == ended.result
    new = step(ended.next_state, dto.RequestResponsePayload(), policy, context)
    assert new.result.code == "INVALID_EVENT"
    assert new.next_state == ended.next_state
    assert new.effects == ()


def test_c24_generating_interruption_advances_epoch_and_ignores_old_result():
    state, policy, context, effect = generating()
    late = run_effect(effect, context, DeterministicDialogueMock())
    interrupted = step(
        state,
        dto.SpeechStartedPayload(human_turn_id=uid("interrupt")),
        policy,
        context,
    )
    assert interrupted.next_state.epoch == state.epoch + 1
    assert interrupted.next_state.pending_effect is None
    assert "cancel_generation" in tuple(effect.kind for effect in interrupted.effects)
    result = reduce_event(
        interrupted.next_state,
        envelope_callback(interrupted.next_state, late, 120),
        policy,
        context,
    )
    assert result.result.disposition == "ignored"
    assert responding_effects(result) == ()
    assert result.next_state.speaking is True


def test_c25_ready_typing_discards_output_without_claiming_delivery():
    state, policy, context, _ = ready()
    transition = step(state, dto.TypingStartedPayload(), policy, context)
    assert transition.next_state.ready_response is None
    assert transition.next_state.question_receipts == ()
    assert responding_effects(transition) == ()


def test_c26_c30_c55_delivery_interrupt_marks_started_not_delivered_and_stops():
    state, policy, context, response = ready()
    begun = begin_delivery(state, policy, context, response)
    assert begun.next_state.question_receipts[0].delivery == "started"
    interrupted = step(
        begun.next_state,
        dto.SpeechStartedPayload(human_turn_id=uid("interrupt")),
        policy,
        context,
    )
    assert "stop_playback" in tuple(effect.kind for effect in interrupted.effects)
    assert interrupted.next_state.active_response is None
    assert interrupted.next_state.question_receipts[0].delivery == "interrupted"
    completed = step(
        interrupted.next_state,
        dto.DeliveryCompletedPayload(receipt=receipt(response, "completed")),
        policy,
        context,
    )
    assert completed.result.disposition == "ignored"
    assert completed.next_state.question_receipts[0].delivery == "interrupted"
    assert responding_effects(completed) == ()


@pytest.mark.parametrize(
    "binding",
    [
        "request_id",
        "response_id",
        "epoch",
        "context_id",
        "context_revision",
        "manifest_id",
        "manifest_version",
        "policy_version",
    ],
)
def test_c27_delivery_receipt_requires_complete_binding(binding):
    state, policy, context, response = ready()
    valid = receipt(response, "started")
    old = getattr(valid, binding)
    wrong = (
        old + 1
        if isinstance(old, int)
        else ("other-policy" if isinstance(old, str) else uid(binding))
    )
    forged = dto.DeliveryReceipt(**(valid.model_dump() | {binding: wrong}))
    transition = step(state, dto.DeliveryStartedPayload(receipt=forged), policy, context)
    assert transition.result.code == "INVALID_RESPONSE"
    assert transition.next_state == state
    assert responding_effects(transition) == ()


@pytest.mark.parametrize("binding", dto.GENERATION_BINDING_FIELDS)
def test_c27_ready_callback_requires_each_original_reservation_field(binding):
    state, policy, context, effect = generating()
    valid = run_effect(effect, context, DeterministicDialogueMock())
    fields = valid.model_dump()
    previous = getattr(valid, binding)
    if binding == "scope":
        fields[binding] = make_scope(actor_user_id=uid("wrong-ready-actor"))
    elif binding == "allowed_outcomes":
        fields[binding] = ("question", "no_reply")
    elif binding == "trigger":
        fields[binding] = "manual"
        fields["allowed_outcomes"] = ("question", "no_reply")
    elif isinstance(previous, int):
        fields[binding] = previous + 1
    elif isinstance(previous, str):
        fields[binding] = "wrong-ready-policy"
    else:
        fields[binding] = uid(f"wrong-ready:{binding}")
    forged = dto.ReadyPayload(**fields)
    refused = step(state, forged, policy, context)
    assert refused.result.code == "INVALID_RESPONSE"
    assert refused.next_state == state
    assert refused.next_state.pending_effect == effect
    assert refused.next_state.ready_response is None
    assert responding_effects(refused) == ()


@pytest.mark.parametrize("stop", [dto.PausePayload(), dto.EndPayload()])
def test_c28_c54_late_callbacks_after_stop_cannot_revive_old_output(stop):
    state, policy, context, effect = generating()
    ready_payload = run_effect(effect, context, DeterministicDialogueMock())
    stopped = step(state, stop, policy, context).next_state
    result = reduce_event(stopped, envelope_callback(stopped, ready_payload, 120), policy, context)
    assert responding_effects(result) == ()
    assert result.next_state.pending_effect is None
    assert result.next_state.ready_response is None
    if stop.kind == "pause":
        assert result.result.disposition == "ignored"
        assert result.next_state.status == "paused"
    else:
        assert result.result.code == "INVALID_EVENT"
        assert result.next_state == stopped


@pytest.mark.parametrize("delivery", ["completed", "interrupted"])
@pytest.mark.parametrize("duplicate", ["key", "normalized-text"])
def test_c29_c30_c55_delivered_or_interrupted_questions_are_not_automatically_repeated(
    delivery, duplicate
):
    provider = DeterministicDialogueMock()
    state, policy, context, response = ready(provider=provider)
    state = begin_delivery(state, policy, context, response).next_state
    if delivery == "completed":
        state = step(
            state,
            dto.DeliveryCompletedPayload(receipt=receipt(response, "completed")),
            policy,
            context,
        ).next_state
    state = step(
        state,
        dto.SpeechStartedPayload(human_turn_id=uid("new-turn")),
        policy,
        context,
    ).next_state
    state = step(
        state,
        dto.SpeechEndedPayload(human_turn_id=uid("new-turn"), semantic_hint="complete"),
        policy,
        context,
    ).next_state
    generated = tick(state, policy, context, time_ms=state.last_time_ms + 100)
    effect = next(item for item in generated.effects if item.kind == "generate")
    key = response.question_key if duplicate == "key" else "different-key"
    text = (
        next(item for item in dto.NEUTRAL_QUESTIONS if item != response.text)
        if duplicate == "key"
        else response.text
    )
    repeated = run_effect(
        effect,
        context,
        DeterministicDialogueMock(question_key=key, text=text),
    )
    result = reduce_event(
        generated.next_state,
        envelope_callback(generated.next_state, repeated, generated.next_state.last_time_ms + 1),
        policy,
        context,
    )
    assert responding_effects(result) == ()
    assert result.next_state.ready_response is None
    assert len(result.next_state.question_receipts) == 1
    assert result.next_state.question_receipts[0].delivery == (
        "delivered" if delivery == "completed" else "interrupted"
    )


def test_c36_c56_capacity_blocks_without_eviction_but_end_has_reserved_receipt():
    policy = make_policy(max_events=3)
    state, policy, context = started(policy=policy)
    state = step(state, dto.TypingStartedPayload(), policy, context).next_state
    blocked = step(state, dto.TypingEndedPayload(), policy, context)
    assert blocked.next_state.status == "blocked"
    assert blocked.result.code == "CONTEXT_LIMIT"
    assert responding_effects(blocked) == ()
    assert len(blocked.next_state.event_receipts) <= policy.max_events
    command = event(blocked.next_state, dto.EndPayload(), expected_version=0)
    ended = reduce_event(blocked.next_state, command, policy, context)
    assert ended.next_state.status == "ended"
    assert ended.next_state.terminal_receipt is not None
    assert len(ended.next_state.event_receipts) <= policy.max_events
    replay = reduce_event(ended.next_state, command, policy, context)
    assert replay.effects == ()
    assert replay.result == ended.result


def test_c39_replace_selection_cancels_old_binding_and_requires_new_manifest_version():
    state, policy, context, effect = generating()
    source = make_source("chosen-note", kind="document_version")
    new_manifest = make_manifest(context.scope, (source.ref,), version=2)
    rebuilt = make_context(sources=(source,), manifest=new_manifest, context_revision=2, history=())
    replaced = step(state, dto.ReplaceSelectionPayload(context=rebuilt), policy, rebuilt)
    assert replaced.result.code == "OK"
    assert replaced.next_state.epoch == state.epoch + 1
    assert replaced.next_state.context_id == rebuilt.id
    assert replaced.next_state.pending_effect is None
    late = run_effect(effect, context, DeterministicDialogueMock())
    stale = reduce_event(
        replaced.next_state,
        envelope_callback(replaced.next_state, late, replaced.next_state.last_time_ms + 1),
        policy,
        rebuilt,
    )
    assert stale.result.disposition == "ignored"
    assert responding_effects(stale) == ()


def test_c40_c57_restriction_blocks_old_context_until_rebuilt_without_dependencies():
    state, policy, context, effect = generating()
    ref = context.source_refs[0]
    restricted = step(state, dto.SourceRestrictedPayload(ref=ref), policy, context)
    assert restricted.next_state.restricted_refs == (ref,)
    assert restricted.next_state.pending_effect is None
    assert "cancel_generation" in tuple(item.kind for item in restricted.effects)
    refused = step(restricted.next_state, dto.RequestResponsePayload(), policy, context)
    assert refused.result.code == "SOURCE_UNAVAILABLE"
    assert responding_effects(refused) == ()
    fresh_source = make_source("new-unrestricted")
    rebuilt = make_context(sources=(fresh_source,), context_revision=2)
    accepted = step(
        refused.next_state,
        dto.UserMessageCommittedPayload(
            human_turn_id=uid("new-text-turn"),
            message_ref=fresh_source.ref,
            semantic_hint="complete",
        ),
        policy,
        rebuilt,
    )
    assert accepted.result.code == "OK"
    assert ref not in rebuilt.source_refs
    assert accepted.next_state.restricted_refs == (ref,)
    late = run_effect(effect, context, DeterministicDialogueMock())
    ignored = reduce_event(
        accepted.next_state,
        envelope_callback(accepted.next_state, late, accepted.next_state.last_time_ms + 1),
        policy,
        rebuilt,
    )
    assert ignored.result.disposition == "ignored"
    assert responding_effects(ignored) == ()
    next_request = step(ignored.next_state, dto.RequestResponsePayload(), policy, rebuilt)
    assert len(responding_effects(next_request)) == 1


def test_c22_pause_before_reservation_does_not_auto_generate_on_resume():
    state, policy, context = quiet_turn()
    assert state.cycle_consumed is False
    paused = step(state, dto.PausePayload(), policy, context)
    resumed = step(paused.next_state, dto.ResumePayload(), policy, context)
    assert resumed.next_state.cycle_consumed is False
    assert resumed.next_state.current_human_turn_id == state.current_human_turn_id
    after_silence = tick(resumed.next_state, policy, context, time_ms=1000)
    assert responding_effects(after_silence) == ()
    assert after_silence.next_state.known_requests == ()
    manual = step(after_silence.next_state, dto.RequestResponsePayload(), policy, context)
    assert len(responding_effects(manual)) == 1
    assert manual.next_state.pending_effect.trigger == "manual"


def test_c57_rebuilt_context_must_remove_old_ai_work_depending_on_restricted_source():
    state, policy, context, effect = generating()
    old_payload = run_effect(effect, context, DeterministicDialogueMock())
    restricted = step(
        state,
        dto.SourceRestrictedPayload(ref=context.source_refs[0]),
        policy,
        context,
    ).next_state
    fresh_source = make_source("fresh-after-restriction")
    user = dto.HistoryItem(
        sequence=1,
        ref=fresh_source.ref,
        role="user",
        text=fresh_source.text,
        delivery="none",
        response_id=None,
    )
    old_ai = dto.HistoryItem(
        sequence=2,
        ref=None,
        role="assistant",
        text=old_payload.response.text,
        delivery="interrupted",
        response_id=old_payload.response.response_id,
    )
    dirty = make_context(sources=(fresh_source,), history=(user, old_ai), context_revision=2)
    commit = dto.UserMessageCommittedPayload(
        human_turn_id=uid("fresh-turn"),
        message_ref=fresh_source.ref,
        semantic_hint="complete",
    )
    refused = step(restricted, commit, policy, dirty)
    assert refused.result.code == "SOURCE_UNAVAILABLE"
    assert refused.next_state == restricted
    assert responding_effects(refused) == ()
    clean = make_context(sources=(fresh_source,), history=(user,), context_revision=2)
    accepted = step(restricted, commit, policy, clean)
    assert accepted.result.code == "OK"
    assert accepted.next_state.context_id == clean.id
    assert clean.recent_history == (user,)
    generate = step(accepted.next_state, dto.RequestResponsePayload(), policy, clean)
    assert len(responding_effects(generate)) == 1
    assert generate.next_state.pending_effect.dependency_refs == (fresh_source.ref,)


def test_c41_skipped_topic_remains_suppressed_until_explicit_unskip():
    state, policy, context = quiet_turn()
    state = step(state, dto.SkipTopicPayload(topic_key="reminiscence"), policy, context).next_state
    assert "reminiscence" in state.skipped_keys
    generated = tick(state, policy, context, time_ms=110)
    effect = next(item for item in generated.effects if item.kind == "generate")
    payload = run_effect(effect, context, DeterministicDialogueMock(topic_key="reminiscence"))
    result = reduce_event(
        generated.next_state,
        envelope_callback(generated.next_state, payload, 111),
        policy,
        context,
    )
    assert responding_effects(result) == ()
    state = step(
        result.next_state, dto.UnskipTopicPayload(topic_key="reminiscence"), policy, context
    ).next_state
    assert "reminiscence" not in state.skipped_keys
    requested = step(state, dto.RequestResponsePayload(), policy, context)
    effect = next(item for item in requested.effects if item.kind == "generate")
    payload = run_effect(effect, context, DeterministicDialogueMock(topic_key="reminiscence"))
    allowed = reduce_event(
        requested.next_state,
        envelope_callback(requested.next_state, payload, requested.next_state.last_time_ms + 1),
        policy,
        context,
    )
    assert allowed.next_state.ready_response is not None


def test_c46_effect_identity_is_deterministic_from_reserved_event():
    first = generating()
    second = generating()
    assert first[0].model_dump_json() == second[0].model_dump_json()
    assert first[3] == second[3]
    state, _, _, effect = first
    triggering = state.event_receipts[-1]
    assert effect.request_id == uuid5(state.scope.session_id, f"generate:{triggering.event_id}")
    assert effect.effect_id == uuid5(effect.request_id, "generate")


@pytest.mark.parametrize("change", [{"version": "other"}, {"max_sources": 19}])
def test_c51_policy_cannot_hot_swap_even_with_unchanged_version(change):
    state, _policy, context = started()
    changed = make_policy(**change)
    transition = step(state, dto.RequestResponsePayload(), changed, context)
    assert transition.result.code == "INVALID_EVENT"
    assert transition.next_state == state
    assert responding_effects(transition) == ()


def test_c52_late_complete_commit_for_a_does_not_overwrite_current_incomplete_b():
    policy = make_policy()
    empty = make_context(sources=(), policy=policy)
    state, policy, _ = quiet_turn(policy=policy, context=empty, name="A")
    state = step(
        state, dto.SpeechStartedPayload(human_turn_id=uid("B")), policy, empty, time_ms=20
    ).next_state
    state = step(
        state,
        dto.SpeechEndedPayload(human_turn_id=uid("B"), semantic_hint="incomplete"),
        policy,
        empty,
        time_ms=30,
    ).next_state
    source = make_source("a-final", origin="voice_final")
    rebuilt = make_context(sources=(source,), policy=policy, context_revision=2)
    late = step(
        state,
        dto.UserMessageCommittedPayload(
            human_turn_id=uid("A"),
            message_ref=source.ref,
            semantic_hint="complete",
        ),
        policy,
        rebuilt,
        time_ms=40,
    )
    assert late.result.code == "OK"
    assert late.next_state.current_human_turn_id == uid("B")
    assert late.next_state.semantic_hint == "incomplete"
    assert late.next_state.silence_since_ms == 30
    assert late.next_state.silence_cycle == 2
    assert len(late.next_state.turn_cycles) == 2
    short = tick(late.next_state, policy, rebuilt, time_ms=130)
    assert responding_effects(short) == ()
    long = tick(short.next_state, policy, rebuilt, time_ms=330)
    effect = next(item for item in long.effects if item.kind == "generate")
    assert effect.allowed_outcomes == ("ack", "no_reply")
    assert long.next_state.silence_since_ms == 30
    assert long.next_state.cycle_consumed is True


def test_c53_callback_accepts_reserved_version_after_legal_intermediate_tick():
    state, policy, context, effect = generating()
    after_tick = tick(state, policy, context, time_ms=120).next_state
    assert after_tick.version > effect.reservation_version
    payload = run_effect(effect, context, DeterministicDialogueMock())
    accepted = reduce_event(
        after_tick, envelope_callback(after_tick, payload, 121), policy, context
    )
    assert accepted.result.code == "OK"
    assert accepted.next_state.ready_response.request_id == effect.request_id
    assert accepted.next_state.ready_response.reservation_version == effect.reservation_version


@pytest.mark.parametrize("callback", ["ready", "failed", "delivery"])
def test_c54_old_bound_callbacks_do_not_block_or_complete_new_request(callback):
    state, policy, context, old_effect = generating()
    old_ready = run_effect(old_effect, context, DeterministicDialogueMock())
    state = step(state, dto.PausePayload(), policy, context).next_state
    state = step(state, dto.ResumePayload(), policy, context).next_state
    state = step(state, dto.RequestResponsePayload(), policy, context).next_state
    new_pending = state.pending_effect
    if callback == "ready":
        payload = old_ready
    elif callback == "failed":
        payload = dto.FailurePayload(
            **dto.generation_binding(old_effect), error_code="PROVIDER_FAILED"
        )
    else:
        payload = dto.DeliveryCompletedPayload(receipt=receipt(old_ready.response, "completed"))
    command = (
        envelope_callback(state, payload, state.last_time_ms + 1)
        if callback != "delivery"
        else event(state, payload)
    )
    command = dto.Event(**(command.model_dump() | {"expected_version": 0}))
    ignored = reduce_event(state, command, policy, context)
    assert ignored.result.disposition == "ignored"
    assert ignored.next_state.status == "generating"
    assert ignored.next_state.pending_effect == new_pending
    assert ignored.next_state.active_response is None
    assert ignored.next_state.version == state.version + 1
    assert responding_effects(ignored) == ()


@pytest.mark.parametrize(
    "stop",
    [
        dto.SpeechStartedPayload(human_turn_id=uid("safe-stop")),
        dto.TypingStartedPayload(),
        dto.PausePayload(),
        dto.EndPayload(),
        dto.SetModePayload(mode="record_only"),
    ],
)
def test_c56_safe_stops_override_only_stale_optimistic_version(stop):
    state, policy, context, _ = generating()
    stopped = step(state, stop, policy, context, expected_version=0)
    assert stopped.result.code == "OK"
    assert stopped.next_state.epoch > state.epoch
    assert stopped.next_state.pending_effect is None
    assert responding_effects(stopped) == ()


def test_c56_source_restriction_also_overrides_stale_version_and_cancels():
    state, policy, context, _ = generating()
    ref = context.source_refs[0]
    stopped = step(
        state,
        dto.SourceRestrictedPayload(ref=ref),
        policy,
        context,
        expected_version=0,
    )
    assert stopped.result.code == "OK"
    assert stopped.next_state.restricted_refs == (ref,)
    assert stopped.next_state.pending_effect is None
    assert stopped.next_state.epoch > state.epoch
    assert "cancel_generation" in tuple(effect.kind for effect in stopped.effects)
    assert responding_effects(stopped) == ()


@pytest.mark.parametrize("kind", ["tick", "callback", "control"])
def test_c58_ordinary_event_cannot_smuggle_a_different_context(kind):
    state, policy, context, effect = generating()
    replacement = make_context(sources=(make_source("smuggled"),), context_revision=2)
    if kind == "tick":
        payload = dto.SilenceElapsedPayload(
            human_turn_id=state.current_human_turn_id,
            silence_cycle=state.silence_cycle,
        )
    elif kind == "callback":
        payload = run_effect(effect, context, DeterministicDialogueMock())
    else:
        payload = dto.ResumePayload()
    refused = step(state, payload, policy, replacement)
    assert refused.result.code == "INVALID_EVENT"
    assert refused.next_state == state
    assert responding_effects(refused) == ()


def test_c58_commit_context_requires_exact_next_revision_and_actual_current_source():
    state, policy, _context = started(context=make_context(sources=()))
    source = make_source("committed")
    payload = dto.UserMessageCommittedPayload(
        human_turn_id=uid("typed-turn"),
        message_ref=source.ref,
        semantic_hint="complete",
    )
    skipped_revision = make_context(sources=(source,), context_revision=3)
    invalid = step(state, payload, policy, skipped_revision)
    assert invalid.result.code == "INVALID_EVENT"
    missing = make_context(sources=(), context_revision=2)
    invalid = step(state, payload, policy, missing)
    assert invalid.result.code in {"INVALID_EVENT", "SOURCE_UNAVAILABLE"}
    correct = make_context(sources=(source,), context_revision=2)
    accepted = step(state, payload, policy, correct)
    assert accepted.result.code == "OK"
    assert accepted.next_state.context_revision == 2
    assert accepted.next_state.committed_refs == (source.ref,)


def test_c35_c58_known_source_cannot_change_body_even_with_fresh_matching_fingerprint():
    state, policy, context = started()
    original = context.sources[0]
    changed = make_source(text="合成替换正文，有效新hash仍不是同一版本。")
    assert changed.ref == original.ref
    assert changed.revision_fingerprint != original.revision_fingerprint
    fresh = make_source("new-valid-commit")
    rebuilt = make_context(sources=(changed, fresh), context_revision=2)
    refused = step(
        state,
        dto.UserMessageCommittedPayload(
            human_turn_id=uid("new-valid-turn"),
            message_ref=fresh.ref,
            semantic_hint="complete",
        ),
        policy,
        rebuilt,
    )
    assert refused.result.code == "INVALID_EVENT"
    assert refused.next_state == state
    assert responding_effects(refused) == ()


@pytest.mark.parametrize("metadata", ["entity-id", "version-number", "origin-scope"])
@pytest.mark.parametrize("restricted", [False, True], ids=["available", "restricted"])
def test_c35_c39_c57_stable_version_identity_cannot_alias_new_metadata(metadata, restricted):
    state, policy, context = started()
    original = context.sources[0]
    if restricted:
        state = step(
            state,
            dto.SourceRestrictedPayload(ref=original.ref),
            policy,
            context,
        ).next_state
    fields = original.ref.model_dump()
    if metadata == "entity-id":
        fields["entity_id"] = uid("alias-entity")
    elif metadata == "version-number":
        fields["version"] = original.ref.version + 1
    else:
        fields["source_scope"] = dto.SourceScope(
            **(
                original.ref.source_scope.model_dump()
                | {
                    "origin_interview_id": uid("alias-old-interview"),
                    "origin_session_id": uid("alias-old-session"),
                }
            )
        )
    alias_ref = dto.SourceVersionRef(**fields)
    alias_text = "合成别名正文，具有自洽hash但不能替换原版本身份。"
    alias = dto.FixtureSource(
        ref=alias_ref,
        text=alias_text,
        availability="available",
        revision_fingerprint=dto.source_fingerprint(alias_text),
    )
    assert (alias.ref.kind, alias.ref.version_id) == (original.ref.kind, original.ref.version_id)
    assert alias.ref != original.ref
    manifest = make_manifest(context.scope, (alias.ref,), version=2)
    replacement = make_context(
        sources=(alias,),
        manifest=manifest,
        context_revision=2,
        history=(),
    )
    refused = step(state, dto.ReplaceSelectionPayload(context=replacement), policy, replacement)
    assert refused.result.code == "INVALID_EVENT"
    assert refused.next_state == state
    assert responding_effects(refused) == ()


@pytest.mark.parametrize("stop", [dto.TypingStartedPayload(), dto.PausePayload(), dto.EndPayload()])
def test_c40_c56_restricted_old_context_is_not_hashed_for_request_or_safety_stop(monkeypatch, stop):
    state, policy, context = started()
    state = step(
        state,
        dto.SourceRestrictedPayload(ref=context.source_refs[0]),
        policy,
        context,
    ).next_state
    original_digest = dto.canonical_digest

    def forbid_context_body_hash(value):
        assert not isinstance(value, dto.ContextSnapshot), (
            "Restricted context body must not be inspected"
        )
        return original_digest(value)

    monkeypatch.setattr(dto, "canonical_digest", forbid_context_body_hash)
    refused = step(state, dto.RequestResponsePayload(), policy, context)
    assert refused.result.code == "SOURCE_UNAVAILABLE"
    assert responding_effects(refused) == ()
    stopped = step(
        refused.next_state,
        stop,
        policy,
        context,
        expected_version=0,
    )
    assert stopped.result.code == "OK"
    assert stopped.next_state.pending_effect is None
    assert stopped.next_state.epoch > refused.next_state.epoch
    assert responding_effects(stopped) == ()


def test_c03_scope_mismatch_rejects_without_any_generation():
    state, policy, context = started()
    foreign = make_scope(actor_user_id=uid("foreign-actor"))
    refused = step(state, dto.RequestResponsePayload(), policy, context, scope=foreign)
    assert refused.result.code == "INVALID_EVENT"
    assert refused.next_state == state
    assert responding_effects(refused) == ()


def test_c44_reducer_does_not_call_io_clock_randomness_or_provider(monkeypatch):
    import builtins
    import os
    import time
    import uuid

    state, policy, context = quiet_turn()
    command = event(
        state,
        dto.SilenceElapsedPayload(
            human_turn_id=state.current_human_turn_id,
            silence_cycle=state.silence_cycle,
        ),
        time_ms=110,
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Pure reducer must not execute I/O or provider effects")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)
    monkeypatch.setattr(time, "time", forbidden)
    monkeypatch.setattr(time, "monotonic", forbidden)
    monkeypatch.setattr(uuid, "uuid4", forbidden)
    monkeypatch.setattr(DeterministicDialogueMock, "generate_response", forbidden)
    transition = reduce_event(state, command, policy, context)
    assert len(responding_effects(transition)) == 1
    assert transition.next_state.status == "generating"
