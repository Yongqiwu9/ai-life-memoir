"""Synthetic immutable source selection and exact-quote context acceptance."""

import pytest
from test_dialogue_contracts import (
    make_context,
    make_manifest,
    make_policy,
    make_scope,
    make_source,
    uid,
)

from app.dialogue import contracts as dto
from app.dialogue.context import build_context


def assert_context_error(expected, **changes):
    defaults = {
        "scope": make_scope(),
        "sources": (make_source(),),
        "manifest": make_manifest(make_scope()),
        "history": (),
        "policy": make_policy(),
        "context_revision": 1,
    }
    with pytest.raises(dto.DialogueError) as captured:
        build_context(**(defaults | changes))
    assert captured.value.code == expected
    assert "合成禁止泄露正文" not in str(captured.value)


@pytest.mark.parametrize("field", ["owner_user_id", "family_id", "family_member_id"])
def test_c03_c50_selected_cross_scope_source_fails_closed(field):
    scope = make_scope()
    original = make_source(kind="document_version").ref.source_scope
    foreign = dto.SourceScope(**(original.model_dump() | {field: uid(f"foreign:{field}")}))
    source = make_source(
        kind="document_version",
        source_scope=foreign,
        text="合成禁止泄露正文",
    )
    assert_context_error(
        "INVALID_EVENT",
        sources=(source,),
        manifest=make_manifest(scope, (source.ref,)),
    )


def test_c32_assistant_history_and_summary_are_not_independent_fact_sources():
    scope, source = make_scope(), make_source()
    quote = dto.SourceQuote(ref=source.ref, start=0, end=4, text=source.text[:4])
    summary = dto.SummaryEntry(quote=quote, label="uncertain")
    user = dto.HistoryItem(
        sequence=1,
        ref=source.ref,
        role="user",
        text=source.text,
        delivery="none",
        response_id=None,
    )
    assistant = dto.HistoryItem(
        sequence=2,
        ref=None,
        role="assistant",
        text="合成AI问题不等于用户经历。",
        delivery="interrupted",
        response_id=uid("assistant-response"),
    )
    context = make_context(
        scope=scope,
        sources=(source,),
        history=(user, assistant),
        summary_entries=(summary,),
    )
    assert context.source_refs == (source.ref,)
    assert context.summary_entries == (summary,)
    assert context.recent_history[-1].role == "assistant"
    assert context.recent_history[-1].delivery == "interrupted"
    assert all(ref.entity_id != uid("assistant-response") for ref in context.source_refs)


def test_c33_uncertainty_negation_and_contradiction_remain_exact_quotes():
    texts = ("合成记录：我没有住过那里。", "合成记录：我可能在另一年去过那里。")
    sources = tuple(make_source(str(i), text) for i, text in enumerate(texts))
    entries = tuple(
        dto.SummaryEntry(
            quote=dto.SourceQuote(ref=source.ref, start=0, end=len(source.text), text=source.text),
            label="conflict",
        )
        for source in sources
    )
    context = make_context(sources=sources, summary_entries=entries)
    assert tuple(entry.quote.text for entry in context.summary_entries) == texts
    assert tuple(entry.label for entry in context.summary_entries) == ("conflict", "conflict")
    assert "1990" not in context.model_dump_json()


def test_c34_history_uses_sequence_and_window_keeps_older_quote_dependency():
    sources = tuple(make_source(str(i), f"合成回忆第{i}段。") for i in range(3))
    history = tuple(
        dto.HistoryItem(
            sequence=i + 1,
            ref=source.ref,
            role="user",
            text=source.text,
            delivery="none",
            response_id=None,
        )
        for i, source in enumerate(sources)
    )
    old = sources[0]
    summary = dto.SummaryEntry(
        quote=dto.SourceQuote(ref=old.ref, start=0, end=len(old.text), text=old.text),
        label="topic",
    )
    context = make_context(
        sources=sources,
        history=tuple(reversed(history)),
        policy=make_policy(max_history_items=2),
        summary_entries=(summary,),
    )
    assert tuple(item.sequence for item in context.recent_history) == (2, 3)
    assert context.summary_entries[0].quote.ref == old.ref
    assert old.ref in context.source_refs


def test_c34_conflicting_history_sequence_is_rejected():
    source = make_source()
    first = dto.HistoryItem(
        sequence=1,
        ref=source.ref,
        role="user",
        text=source.text,
        delivery="none",
        response_id=None,
    )
    other = dto.HistoryItem(
        sequence=1,
        ref=None,
        role="assistant",
        text="另一条合成内容。",
        delivery="delivered",
        response_id=uid("different-response"),
    )
    assert_context_error("INVALID_EVENT", sources=(source,), history=(first, other))


@pytest.mark.parametrize(
    "start,end,text",
    [(1, 4, "合成讲述"), (0, 3, "合成讲述"), (0, 4, "伪造引文"), (0, 500, "合成讲述")],
    ids=("wrong-start", "wrong-end", "wrong-text", "past-source"),
)
def test_c35_quote_offsets_and_text_must_all_match(start, end, text):
    source = make_source()
    entry = dto.SummaryEntry(
        quote=dto.SourceQuote(ref=source.ref, start=start, end=end, text=text),
        label="topic",
    )
    assert_context_error("INVALID_EVENT", summary_entries=(entry,))


def test_c35_same_ref_changed_body_cannot_pass_original_fingerprint():
    source = make_source()
    forged = dto.FixtureSource(
        ref=source.ref,
        text="合成改写，不是原版本。",
        availability="available",
        revision_fingerprint=source.revision_fingerprint,
    )
    assert_context_error(
        "INVALID_EVENT",
        sources=(forged,),
        manifest=make_manifest(make_scope(), (forged.ref,)),
    )


@pytest.mark.parametrize("limit", ["max_sources", "max_context_chars", "max_summary_entries"])
def test_c36_context_limits_do_not_silently_drop_dependencies(limit):
    sources = (make_source("one"), make_source("two"))
    entries = tuple(
        dto.SummaryEntry(
            quote=dto.SourceQuote(ref=source.ref, start=0, end=4, text=source.text[:4]),
            label="topic",
        )
        for source in sources
    )
    assert_context_error(
        "CONTEXT_LIMIT",
        sources=sources,
        manifest=make_manifest(make_scope(), tuple(s.ref for s in sources)),
        policy=make_policy(**{limit: 1}),
        summary_entries=entries,
    )


def test_c37_unselected_diary_and_older_session_never_enter_context():
    current = make_source()
    diary = make_source("unselected-diary", "合成禁止泄露正文", kind="document_version")
    foreign_session = make_scope(session_id=uid("old-session"))
    older = make_source("unselected-old", "合成禁止泄露正文", scope=foreign_session)
    context = make_context(sources=(current, diary, older))
    assert context.source_refs == (current.ref,)
    assert "合成禁止泄露正文" not in context.model_dump_json()


def test_c38_manifest_pins_version_even_when_catalog_contains_new_versions_and_members():
    scope = make_scope()
    v1 = make_source("diary", "合成日记第一版。", kind="document_version", version=1)
    v2 = make_source("diary", "合成日记第二版。", kind="document_version", version=2)
    extra = make_source("new-member", "合成新增资料。", kind="document_version")
    manifest = make_manifest(scope, (v1.ref,))
    old = make_context(sources=(v1,), manifest=manifest, history=())
    updated_catalog = make_context(sources=(v1, v2, extra), manifest=manifest, history=())
    assert old.model_dump_json() == updated_catalog.model_dump_json()
    assert updated_catalog.source_refs == (v1.ref,)
    assert v2.ref not in updated_catalog.source_refs
    assert extra.ref not in updated_catalog.source_refs


def test_c42_c50_document_preserves_independent_id_without_fake_session_or_message():
    document = make_source("diary", kind="document_version")
    context = make_context(
        sources=(document,),
        manifest=make_manifest(make_scope(), (document.ref,)),
        history=(),
    )
    ref = context.source_refs[0]
    assert ref.kind == "document_version"
    assert ref.origin == "document"
    assert ref.entity_id == document.ref.entity_id
    assert ref.source_scope.origin_interview_id is None
    assert ref.source_scope.origin_session_id is None
    assert context.recent_history == ()


def test_c49_selected_old_session_keeps_its_original_scope():
    current = make_scope()
    older_scope = make_scope(interview_id=uid("old-interview"), session_id=uid("old-session"))
    older = make_source("selected-old", scope=older_scope)
    context = make_context(
        scope=current,
        sources=(older,),
        manifest=make_manifest(current, (older.ref,)),
        history=(),
    )
    assert context.source_refs == (older.ref,)
    assert context.source_refs[0].source_scope.origin_session_id == older_scope.session_id
    assert context.source_refs[0].source_scope.origin_session_id != current.session_id


def test_c51_extraction_manifest_is_not_dialogue_permission():
    assert_context_error(
        "INVALID_EVENT",
        manifest=make_manifest(make_scope(), purpose="extraction"),
    )


def test_c44_context_builder_performs_no_file_environment_or_clock_reads(monkeypatch):
    import builtins
    import os
    import time
    import uuid

    scope, policy, source = make_scope(), make_policy(), make_source()
    manifest = make_manifest(scope, (source.ref,))

    def forbidden(*args, **kwargs):
        raise AssertionError("I/O, environment, real clock and randomness are forbidden")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)
    monkeypatch.setattr(time, "time", forbidden)
    monkeypatch.setattr(time, "monotonic", forbidden)
    monkeypatch.setattr(uuid, "uuid4", forbidden)
    context = build_context(
        scope=scope,
        sources=(source,),
        manifest=manifest,
        history=(),
        policy=policy,
        context_revision=1,
    )
    assert context.source_refs == (source.ref,)
