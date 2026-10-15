"""Explicit offline runner, full binding and non-fabricating output tests."""

from uuid import uuid5

import pytest
from pydantic import ValidationError
from test_dialogue_contracts import make_context, make_policy, make_scope, make_source, uid

from app.dialogue import contracts as dto
from app.dialogue.controller import create_state
from app.dialogue.mock import DeterministicDialogueMock
from app.dialogue.provider import sourced_question
from app.dialogue.runner import envelope_callback, run_effect, validate_response


def reserved(context=None, *, trigger="auto", allowed_outcomes=("ack", "question", "no_reply")):
    context = context or make_context()
    request_id = uuid5(context.scope.session_id, f"generate:{uid('reserved-event')}")
    effect = dto.GenerateEffect(
        effect_id=uuid5(request_id, "generate"),
        request_id=request_id,
        scope=context.scope,
        reservation_version=5,
        policy_version=make_policy().version,
        epoch=2,
        context_id=context.id,
        context_revision=context.context_revision,
        manifest_id=context.manifest_id,
        manifest_version=context.manifest_version,
        silence_cycle=1,
        trigger=trigger,
        allowed_outcomes=allowed_outcomes,
        dependency_refs=context.source_refs,
    )
    return effect, context


def test_c43_no_provider_returns_fixed_refusal_without_fallback():
    effect, context = reserved()
    payload = run_effect(effect, context)
    assert isinstance(payload, dto.FailurePayload)
    assert payload.error_code == "INVALID_EVENT"
    assert payload.request_id == effect.request_id
    assert "provider" not in payload.model_dump()
    assert not hasattr(payload, "response")


def test_c43_explicit_stub_is_called_once_and_runner_does_not_own_state():
    effect, context = reserved()
    provider = DeterministicDialogueMock()
    before = context.model_dump_json(), effect.model_dump_json()
    payload = run_effect(effect, context, provider)
    assert provider.calls == 1
    assert isinstance(payload, dto.ReadyPayload)
    assert before == (context.model_dump_json(), effect.model_dump_json())
    assert payload.response.response_id == uuid5(effect.request_id, "response")
    assert not any(hasattr(payload, name) for name in ("seq", "time_ms", "expected_version"))


@pytest.mark.parametrize("outcome", ["ack", "question", "no_reply"])
def test_c09_c31_valid_results_echo_every_reserved_binding(outcome):
    effect, context = reserved()
    payload = run_effect(effect, context, DeterministicDialogueMock(outcome=outcome))
    assert isinstance(payload, dto.ReadyPayload)
    for name in dto.GENERATION_BINDING_FIELDS:
        assert getattr(payload, name) == getattr(effect, name)
        assert getattr(payload.response, name) == getattr(effect, name)
    assert payload.response.effect_id == effect.effect_id
    assert payload.response.outcome == outcome
    if outcome == "ack":
        assert payload.response.text in dto.ACK_TEXTS
        assert payload.response.basis_kind == "none"
        assert payload.response.basis_quotes == ()
        assert payload.response.question_key is None
    elif outcome == "no_reply":
        assert payload.response.text is None
        assert payload.response.question_key is None
        assert payload.response.topic_key is None
        assert payload.response.basis_kind == "none"
    else:
        assert payload.response.text in dto.NEUTRAL_QUESTIONS
        assert payload.response.basis_kind == "neutral"
        assert payload.response.basis_quotes == ()


@pytest.mark.parametrize(
    "field", list(dto.GENERATION_BINDING_FIELDS) + ["effect_id", "response_id"]
)
def test_c27_response_binding_rejects_each_mismatched_field(field):
    effect, context = reserved()
    valid = DeterministicDialogueMock().generate_response(effect, context)
    original = getattr(valid, field)
    if field == "scope":
        replacement = make_scope(actor_user_id=uid("other-actor"))
    elif field == "allowed_outcomes":
        replacement = ("question", "no_reply")
    elif field == "trigger":
        replacement = "manual"
    elif isinstance(original, int):
        replacement = original + 1
    elif isinstance(original, str):
        replacement = "other-policy"
    else:
        replacement = uid(f"other:{field}")
    forged = dto.Response.model_construct(**(valid.model_dump() | {field: replacement}))
    with pytest.raises(dto.DialogueError) as captured:
        validate_response(forged, effect, context)
    assert captured.value.code == "INVALID_RESPONSE"
    provider = DeterministicDialogueMock(script=(forged,))
    failed = run_effect(effect, context, provider)
    assert failed.error_code == "INVALID_RESPONSE"
    assert provider.calls == 1


@pytest.mark.parametrize(
    "text", ["您当年一定很悲伤。", "您1990年住在海边吗？"], ids=("emotion", "biography")
)
def test_c31_ack_rejects_emotion_or_biography_assertion(text):
    effect, context = reserved()
    payload = run_effect(effect, context, DeterministicDialogueMock(outcome="ack", text=text))
    assert isinstance(payload, dto.FailurePayload)
    assert payload.error_code == "INVALID_RESPONSE"
    assert text not in payload.model_dump_json()


def test_c31_question_cannot_invent_neutral_biographical_claims():
    effect, context = reserved()
    payload = run_effect(
        effect,
        context,
        DeterministicDialogueMock(text="您第一次坐飞机去国外时发生了什么？"),
    )
    assert isinstance(payload, dto.FailurePayload)
    assert payload.error_code == "INVALID_RESPONSE"


def test_c33_sourced_question_preserves_exact_uncertain_negative_source():
    source = make_source(text="合成记忆：我不确定日期，也没说自己去过海边。")
    context = make_context(sources=(source,))
    effect, context = reserved(context)
    payload = run_effect(effect, context, DeterministicDialogueMock(basis_kind="sourced"))
    assert isinstance(payload, dto.ReadyPayload)
    response = payload.response
    assert response.basis_kind == "sourced"
    assert response.basis_quotes == (
        dto.SourceQuote(ref=source.ref, start=0, end=len(source.text), text=source.text),
    )
    assert response.text == sourced_question(source.text)
    assert "不确定" in response.text and "没说" in response.text


def test_c32_c35_summary_or_assistant_text_cannot_replace_original_quote():
    effect, context = reserved()
    source = context.sources[0]
    invented = dto.SourceQuote(ref=source.ref, start=0, end=4, text="AI编写")
    payload = run_effect(
        effect,
        context,
        DeterministicDialogueMock(basis_kind="sourced", basis_quotes=(invented,)),
    )
    assert isinstance(payload, dto.FailurePayload)
    assert payload.error_code == "INVALID_RESPONSE"
    assert "AI编写" not in payload.model_dump_json()


def test_c10_stub_cannot_return_question_when_only_ack_or_no_reply_allowed():
    effect, context = reserved(allowed_outcomes=("ack", "no_reply"))
    payload = run_effect(effect, context, DeterministicDialogueMock(outcome="question"))
    assert isinstance(payload, dto.FailurePayload)
    assert payload.error_code == "INVALID_RESPONSE"


def test_c45_exception_is_not_logged_printed_or_copied_and_no_retry_occurs(caplog, capsys):
    effect, context = reserved()
    provider = DeterministicDialogueMock(script=(TimeoutError("合成禁止泄露正文和密钥"),))
    payload = run_effect(effect, context, provider)
    assert payload.error_code == "PROVIDER_FAILED"
    assert provider.calls == 1
    assert "合成禁止泄露正文和密钥" not in payload.model_dump_json()
    assert caplog.text == ""
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


def test_c45_malformed_provider_shape_is_fixed_invalid_response():
    class MalformedProvider:
        calls = 0

        def generate_response(self, effect, context):
            self.calls += 1
            return {"answer": "合成禁止泄露正文"}

    effect, context = reserved()
    provider = MalformedProvider()
    payload = run_effect(effect, context, provider)
    assert provider.calls == 1
    assert payload.error_code == "INVALID_RESPONSE"
    assert "合成禁止泄露正文" not in payload.model_dump_json()


def test_c53_callback_uses_current_envelope_and_preserves_reservation_binding():
    effect, context = reserved()
    state = create_state(context.scope, make_policy(), context)
    state = dto.DialogueState(**(state.model_dump() | {"version": 12, "last_seq": 19}))
    payload = run_effect(effect, context, DeterministicDialogueMock())
    callback = envelope_callback(state, payload, 777)
    assert callback.seq == 20
    assert callback.expected_version == 12
    assert callback.time_ms == 777
    assert callback.payload.reservation_version == 5
    assert callback.scope == state.scope
    assert callback.event_id == uuid5(effect.request_id, "callback:response_ready:20")
    assert envelope_callback(state, payload, 777) == callback


def test_c43_callback_rejects_foreign_scope_and_bool_time():
    effect, context = reserved()
    payload = run_effect(effect, context, DeterministicDialogueMock())
    state = create_state(context.scope, make_policy(), context)
    with pytest.raises(dto.DialogueError) as captured:
        envelope_callback(state, payload, True)
    assert captured.value.code == "INVALID_EVENT"
    foreign_scope = make_scope(actor_user_id=uid("foreign"))
    forged = dto.ReadyPayload.model_construct(**(payload.model_dump() | {"scope": foreign_scope}))
    with pytest.raises(dto.DialogueError) as captured:
        envelope_callback(state, forged, 1)
    assert captured.value.code == "INVALID_EVENT"


def test_c40_runner_rejects_restricted_source_without_calling_provider():
    effect, context = reserved()
    original = context.sources[0]
    restricted = dto.FixtureSource(**(original.model_dump() | {"availability": "restricted"}))
    unavailable = dto.ContextSnapshot.model_construct(
        **(context.model_dump() | {"sources": (restricted,)})
    )
    provider = DeterministicDialogueMock()
    payload = run_effect(effect, unavailable, provider)
    assert payload.error_code == "SOURCE_UNAVAILABLE"
    assert provider.calls == 0


@pytest.mark.parametrize(
    "invalidity", ["duplicate-sequence", "descending-sequence", "stable-key-alias"]
)
def test_c34_c35_runner_rechecks_semantic_context_before_invoking_stub(invalidity):
    sources = (make_source("first"), make_source("second"))
    original = make_context(sources=sources)
    values = {name: getattr(original, name) for name in type(original).model_fields if name != "id"}
    if invalidity == "duplicate-sequence":
        first, second = original.recent_history
        duplicate = dto.HistoryItem(**(second.model_dump() | {"sequence": first.sequence}))
        values["recent_history"] = (first, duplicate)
    elif invalidity == "descending-sequence":
        values["recent_history"] = tuple(reversed(original.recent_history))
    else:
        source = original.sources[0]
        alias_ref = dto.SourceVersionRef(**(source.ref.model_dump() | {"entity_id": uid("alias")}))
        alias_text = "合成别名来源。"
        alias = dto.FixtureSource(
            ref=alias_ref,
            text=alias_text,
            availability="available",
            revision_fingerprint=dto.source_fingerprint(alias_text),
        )
        values["source_refs"] = (*original.source_refs, alias_ref)
        values["sources"] = (*original.sources, alias)
    # Recompute a correct content ID so this exercises semantic validation,
    # rather than accidentally passing only because an old ID was retained.
    expected_id = uuid5(original.scope.session_id, f"context:{dto.canonical_digest(values)}")
    malformed = dto.ContextSnapshot.model_construct(id=expected_id, **values)
    effect, _ = reserved(malformed)
    provider = DeterministicDialogueMock()
    payload = run_effect(effect, malformed, provider)
    assert payload.error_code == "INVALID_EVENT"
    assert provider.calls == 0


def test_c48_import_surface_has_no_backend_db_network_sdk_or_configuration_module():
    from types import ModuleType

    from app.dialogue import context, contracts, controller, mock, provider, runner

    forbidden = {"requests", "httpx", "socket", "sqlalchemy", "psycopg", "openai", "dotenv"}
    for module in (context, contracts, controller, mock, provider, runner):
        modules = tuple(value for value in vars(module).values() if isinstance(value, ModuleType))
        assert not any(value.__name__.split(".")[0] in forbidden for value in modules)
        assert not any(value.__name__.startswith("app.core.config") for value in modules)


def test_c01_event_envelope_rejects_bool_int_and_untyped_extra_payload():
    state = create_state(make_scope(), make_policy(), make_context())
    values = {
        "event_id": uid("strict-event"),
        "seq": 1,
        "time_ms": 0,
        "scope": state.scope,
        "expected_version": 0,
        "payload": dto.StartPayload(),
    }
    for name in ("seq", "time_ms", "expected_version"):
        with pytest.raises(ValidationError):
            dto.Event(**(values | {name: True}))
    with pytest.raises(ValidationError):
        dto.Event(**(values | {"payload": {"kind": "start", "trusted": True}}))


def test_c55_normalization_is_nfkc_casefold_and_removes_whitespace_and_punctuation():
    original = " ＡＢＣ， 你 好？ "
    assert dto.normalize_question(original) == "abc你好"
    assert dto.normalize_question("abc你好!") == dto.normalize_question(original)
    assert original == " ＡＢＣ， 你 好？ "
