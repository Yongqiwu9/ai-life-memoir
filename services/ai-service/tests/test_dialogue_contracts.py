"""Strict, immutable synthetic dialogue DTO tests and deterministic shared fixtures."""

from uuid import NAMESPACE_URL, uuid5

import pytest
from pydantic import ValidationError

from app.dialogue import contracts as dto
from app.dialogue.context import build_context, source_fingerprint


def uid(name):
    return uuid5(NAMESPACE_URL, f"ai-life-memoir:c1:synthetic:{name}")


def make_scope(**changes):
    fields = {
        "actor_user_id": uid("actor"),
        "family_id": uid("family"),
        "family_member_id": uid("member"),
        "interview_id": uid("interview"),
        "session_id": uid("session"),
    }
    return dto.DialogueScope(**(fields | changes))


def make_policy(**changes):
    fields = {
        "version": "synthetic-test-policy-v1",
        "complete_pause_ms": 100,
        "uncertain_pause_ms": 300,
        "max_events": 200,
        "max_sources": 20,
        "max_context_chars": 12000,
        "max_history_items": 10,
        "max_summary_entries": 10,
        "mode": "light",
    }
    return dto.Policy(**(fields | changes))


def make_source(
    name="one",
    text="合成讲述：我不确定那一年，只记得练习过种花。",
    *,
    scope=None,
    source_scope=None,
    kind="message",
    origin="user_text",
    version=1,
    availability="available",
):
    scope = scope or make_scope()
    if source_scope is None:
        source_scope = dto.SourceScope(
            owner_user_id=scope.actor_user_id,
            family_id=scope.family_id,
            family_member_id=scope.family_member_id,
            origin_interview_id=scope.interview_id if kind == "message" else None,
            origin_session_id=scope.session_id if kind == "message" else None,
        )
    if kind == "document_version":
        origin = "document"
    ref = dto.SourceVersionRef(
        kind=kind,
        entity_id=uid(f"{name}:entity"),
        version_id=uid(f"{name}:version:{version}"),
        version=version,
        source_scope=source_scope,
        origin=origin,
    )
    return dto.FixtureSource(
        ref=ref,
        text=text,
        availability=availability,
        revision_fingerprint=source_fingerprint(text),
    )


def make_manifest(scope, refs=(), *, version=1, purpose="dialogue", name="selection"):
    return dto.SelectionManifest(
        id=uid(name),
        version=version,
        purpose=purpose,
        ordered_refs=tuple(refs),
        scope=scope,
    )


def make_context(
    *,
    scope=None,
    sources=None,
    manifest=None,
    history=None,
    policy=None,
    context_revision=1,
    summary_entries=(),
    asked_keys=(),
    skipped_keys=(),
):
    scope = scope or make_scope()
    policy = policy or make_policy()
    sources = (make_source(scope=scope),) if sources is None else tuple(sources)
    manifest = manifest or make_manifest(scope)
    if history is None:
        history = tuple(
            dto.HistoryItem(
                sequence=index + 1,
                ref=source.ref,
                role="user",
                text=source.text,
                delivery="none",
                response_id=None,
            )
            for index, source in enumerate(sources)
            if source.ref.kind == "message"
            and source.ref.source_scope.origin_session_id == scope.session_id
        )
    return build_context(
        scope=scope,
        sources=sources,
        manifest=manifest,
        history=tuple(history),
        policy=policy,
        context_revision=context_revision,
        summary_entries=tuple(summary_entries),
        asked_keys=tuple(asked_keys),
        skipped_keys=tuple(skipped_keys),
    )


def event(state, payload, *, time_ms=None, **changes):
    fields = {
        "event_id": uid(f"event:{state.last_seq + 1}:{payload.kind}"),
        "seq": state.last_seq + 1,
        "time_ms": state.last_time_ms + 1 if time_ms is None else time_ms,
        "scope": state.scope,
        "expected_version": state.version,
        "payload": payload,
    }
    return dto.Event(**(fields | changes))


def step(state, payload, policy, context, **changes):
    from app.dialogue.controller import reduce_event

    return reduce_event(state, event(state, payload, **changes), policy, context)


def test_ir02_c01_source_availability_requires_explicit_fixture_decision():
    fields = make_source().model_dump()
    fields.pop("availability")
    with pytest.raises(ValidationError) as captured:
        dto.FixtureSource.model_validate(fields)
    assert any(
        error["loc"] == ("availability",) and error["type"] == "missing"
        for error in captured.value.errors()
    )
    for availability in ("available", "restricted"):
        source = dto.FixtureSource.model_validate({**fields, "availability": availability})
        assert source.availability == availability


def test_c01_extra_fields_rejected_at_scope_and_nested_source():
    with pytest.raises(ValidationError):
        dto.DialogueScope(**(make_scope().model_dump() | {"synthetic": True}))
    source = make_source().model_dump()
    source["ref"]["claimed_consent"] = True
    with pytest.raises(ValidationError):
        dto.FixtureSource.model_validate(source)


@pytest.mark.parametrize("field", ["complete_pause_ms", "max_events", "max_sources"])
@pytest.mark.parametrize("value", [True, False, 0, -1, "3", 1.5])
def test_c01_policy_integer_limits_are_strict_positive(field, value):
    with pytest.raises(ValidationError):
        make_policy(**{field: value})


@pytest.mark.parametrize("version", [True, False, 0, -1, "1", 1.5])
def test_c01_source_version_rejects_bool_and_coercion(version):
    with pytest.raises(ValidationError):
        make_source(version=version)


@pytest.mark.parametrize(
    "text",
    ["", " ", "\t\n", "x" * 100001],
    ids=["empty", "spaces", "controls", "oversize"],
)
def test_c01_source_body_rejects_empty_or_oversize_without_rewriting(text):
    with pytest.raises(ValidationError):
        make_source(text=text)


def test_c01_policy_requires_all_parameters_and_ordered_pause_thresholds():
    fields = make_policy().model_dump()
    del fields["mode"]
    with pytest.raises(ValidationError):
        dto.Policy(**fields)
    with pytest.raises(ValidationError):
        make_policy(complete_pause_ms=301, uncertain_pause_ms=300)


def test_c01_manifest_rejects_duplicate_refs():
    source = make_source()
    with pytest.raises(ValidationError):
        make_manifest(make_scope(), (source.ref, source.ref))


def test_c01_c38_context_selection_rejects_duplicate_refs_directly():
    source = make_source()
    manifest = make_manifest(make_scope(), (source.ref,))
    context = make_context(sources=(source,), manifest=manifest)
    with pytest.raises(ValidationError):
        dto.ContextSnapshot.model_validate(
            context.model_dump() | {"selection_refs": (source.ref, source.ref)}
        )


def test_c02_sources_manifest_context_and_nested_scope_are_frozen():
    source = make_source(text="  合成原文保留空格。  ")
    scope = make_scope()
    manifest = make_manifest(scope, (source.ref,))
    context = make_context(sources=(source,), manifest=manifest)
    before = (source.model_dump_json(), manifest.model_dump_json(), context.model_dump_json())
    for target, field, value in [
        (source, "text", "覆盖"),
        (source.ref.source_scope, "family_id", uid("other-family")),
        (manifest, "ordered_refs", ()),
        (context, "source_refs", ()),
    ]:
        with pytest.raises(ValidationError):
            setattr(target, field, value)
    assert before == (
        source.model_dump_json(),
        manifest.model_dump_json(),
        context.model_dump_json(),
    )
    assert source.text == "  合成原文保留空格。  "
    assert isinstance(context.source_refs, tuple)


def test_c01_constructed_invalid_nested_instance_is_revalidated():
    invalid = dto.SourceScope.model_construct(
        **(make_source().ref.source_scope.model_dump() | {"family_id": "not-a-uuid"})
    )
    values = make_source().ref.model_dump() | {"source_scope": invalid}
    with pytest.raises(ValidationError):
        dto.SourceVersionRef(**values)


def test_c42_c50_document_origin_does_not_allow_half_filled_fake_session_scope():
    original = make_source(kind="document_version").ref.source_scope.model_dump()
    with pytest.raises(ValidationError):
        dto.SourceScope(**(original | {"origin_session_id": uid("fake-origin")}))
    source = make_source(kind="document_version")
    with pytest.raises(ValidationError):
        dto.SourceVersionRef(**(source.ref.model_dump() | {"origin": "user_text"}))


def test_c46_synthetic_fixture_generation_is_repeatable():
    first = make_context()
    second = make_context()
    assert first.model_dump_json() == second.model_dump_json()
    assert make_source().ref.version_id == make_source().ref.version_id
    assert first.scope.session_id == uid("session")
