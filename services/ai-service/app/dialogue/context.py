"""Pure fixture selection, exact quote validation and bounded working context."""

from uuid import uuid5

from pydantic import ValidationError

from .contracts import (
    ContextSnapshot,
    DialogueError,
    DialogueScope,
    FixtureSource,
    HistoryItem,
    Policy,
    SelectionManifest,
    SourceQuote,
    SourceVersionRef,
    SummaryEntry,
    canonical_digest,
    source_fingerprint,
)


def source_scope_matches(ref: SourceVersionRef, scope: DialogueScope) -> bool:
    """Compare only the explicitly defined synthetic owner/member projection."""
    return (
        ref.source_scope.owner_user_id == scope.actor_user_id
        and ref.source_scope.family_id == scope.family_id
        and ref.source_scope.family_member_id == scope.family_member_id
    )


def _current_message(ref: SourceVersionRef, scope: DialogueScope) -> bool:
    return (
        ref.kind == "message"
        and ref.source_scope.origin_interview_id == scope.interview_id
        and ref.source_scope.origin_session_id == scope.session_id
    )


def _unique(values):
    return tuple(dict.fromkeys(values))


def validate_quote(quote: SourceQuote, sources: tuple[FixtureSource, ...]) -> SourceQuote:
    """Validate a code-point slice against the original immutable fixture text."""
    try:
        quote = SourceQuote.model_validate(quote)
        matches = tuple(source for source in sources if source.ref == quote.ref)
        if len(matches) != 1 or matches[0].availability != "available":
            raise DialogueError("SOURCE_UNAVAILABLE")
        source = matches[0]
        if source.revision_fingerprint != source_fingerprint(source.text):
            raise DialogueError("INVALID_EVENT")
        if quote.end > len(source.text) or source.text[quote.start : quote.end] != quote.text:
            raise DialogueError("INVALID_EVENT")
    except ValidationError:
        raise DialogueError("INVALID_EVENT") from None
    return quote


def _validate_source(source: FixtureSource, scope: DialogueScope) -> None:
    # Scope and availability are inspected before touching the fixture body.
    if not source_scope_matches(source.ref, scope):
        raise DialogueError("INVALID_EVENT")
    if source.availability != "available":
        raise DialogueError("SOURCE_UNAVAILABLE")
    if source.revision_fingerprint != source_fingerprint(source.text):
        raise DialogueError("INVALID_EVENT")


def _limits(context: ContextSnapshot, policy: Policy) -> None:
    if (
        len(context.source_refs) > policy.max_sources
        or len(context.recent_history) > policy.max_history_items
        or len(context.summary_entries) > policy.max_summary_entries
        or len(context.asked_keys) > policy.max_events
        or len(context.skipped_keys) > policy.max_events
    ):
        raise DialogueError("CONTEXT_LIMIT")
    # Count actual stored text, including duplicate quote/history representations.
    char_count = (
        sum(len(source.text) for source in context.sources)
        + sum(len(item.text) for item in context.recent_history)
        + sum(len(entry.quote.text) for entry in context.summary_entries)
        + sum(len(key) for key in context.asked_keys + context.skipped_keys)
    )
    if char_count > policy.max_context_chars:
        raise DialogueError("CONTEXT_LIMIT")


def validate_context(context: ContextSnapshot, policy: Policy) -> ContextSnapshot:
    """Revalidate an already built snapshot without reading any external source."""
    try:
        context = ContextSnapshot.model_validate(context)
        policy = Policy.model_validate(policy)
    except ValidationError:
        raise DialogueError("INVALID_EVENT") from None
    selected = set(context.selection_refs)
    revision_ids = tuple((ref.kind, ref.version_id) for ref in context.source_refs)
    if len(set(revision_ids)) != len(revision_ids):
        raise DialogueError("INVALID_EVENT")
    for source in context.sources:
        if not source_scope_matches(source.ref, context.scope):
            raise DialogueError("INVALID_EVENT")
        if not _current_message(source.ref, context.scope) and source.ref not in selected:
            raise DialogueError("INVALID_EVENT")
        _validate_source(source, context.scope)
    seen_sequences = set()
    for item in context.recent_history:
        if item.sequence in seen_sequences:
            raise DialogueError("INVALID_EVENT")
        seen_sequences.add(item.sequence)
        if item.role == "user":
            source = next((source for source in context.sources if source.ref == item.ref), None)
            if source is None:
                raise DialogueError("SOURCE_UNAVAILABLE")
            if item.text != source.text:
                raise DialogueError("INVALID_EVENT")
    if (
        tuple(sorted(context.recent_history, key=lambda item: item.sequence))
        != context.recent_history
    ):
        raise DialogueError("INVALID_EVENT")
    for entry in context.summary_entries:
        validate_quote(entry.quote, context.sources)
    _limits(context, policy)
    payload = {name: getattr(context, name) for name in type(context).model_fields if name != "id"}
    if context.id != uuid5(context.scope.session_id, f"context:{canonical_digest(payload)}"):
        raise DialogueError("INVALID_EVENT")
    return context


def build_context(
    *,
    scope: DialogueScope,
    sources: tuple[FixtureSource, ...],
    manifest: SelectionManifest,
    history: tuple[HistoryItem, ...],
    policy: Policy,
    context_revision: int,
    summary_entries: tuple[SummaryEntry, ...] = (),
    asked_keys: tuple[str, ...] = (),
    skipped_keys: tuple[str, ...] = (),
) -> ContextSnapshot:
    """Freeze permitted references and bounded exact-quote working context.

    The supplied directory is a test fixture, not a SourceRegistry or an access
    grant. Unselected directory entries are not inspected for text or included.
    """
    try:
        scope = DialogueScope.model_validate(scope)
        policy = Policy.model_validate(policy)
        manifest = SelectionManifest.model_validate(manifest)
    except ValidationError:
        raise DialogueError("INVALID_EVENT") from None
    if manifest.scope != scope or manifest.purpose != "dialogue":
        raise DialogueError("INVALID_EVENT")
    if type(context_revision) is not int or context_revision <= 0:
        raise DialogueError("INVALID_EVENT")
    if any(
        not isinstance(value, tuple)
        for value in (sources, history, summary_entries, asked_keys, skipped_keys)
    ):
        raise DialogueError("INVALID_EVENT")

    ordered_history: dict[int, HistoryItem] = {}
    for item in history:
        try:
            item = HistoryItem.model_validate(item)
        except ValidationError:
            raise DialogueError("INVALID_EVENT") from None
        previous = ordered_history.get(item.sequence)
        if previous is not None and previous != item:
            raise DialogueError("INVALID_EVENT")
        ordered_history[item.sequence] = item
    all_history = tuple(ordered_history[index] for index in sorted(ordered_history))
    selected = set(manifest.ordered_refs)
    for ref in manifest.ordered_refs:
        if not source_scope_matches(ref, scope):
            raise DialogueError("INVALID_EVENT")
    history_refs = tuple(item.ref for item in all_history if item.role == "user")
    for ref in history_refs:
        if not source_scope_matches(ref, scope) or (
            not _current_message(ref, scope) and ref not in selected
        ):
            raise DialogueError("INVALID_EVENT")
    for entry in summary_entries:
        try:
            SummaryEntry.model_validate(entry)
        except ValidationError:
            raise DialogueError("INVALID_EVENT") from None
        ref = entry.quote.ref
        if not source_scope_matches(ref, scope) or (
            not _current_message(ref, scope) and ref not in selected
        ):
            raise DialogueError("INVALID_EVENT")

    refs = _unique(
        manifest.ordered_refs + history_refs + tuple(e.quote.ref for e in summary_entries)
    )
    if len(refs) > policy.max_sources:
        raise DialogueError("CONTEXT_LIMIT")
    included = []
    for ref in refs:
        candidates = tuple(source for source in sources if source.ref == ref)
        if not candidates:
            raise DialogueError("SOURCE_UNAVAILABLE")
        if any(source != candidates[0] for source in candidates[1:]):
            raise DialogueError("INVALID_EVENT")
        try:
            source = FixtureSource.model_validate(candidates[0])
        except ValidationError:
            raise DialogueError("INVALID_EVENT") from None
        _validate_source(source, scope)
        included.append(source)
    included_sources = tuple(included)
    for item in all_history:
        if item.role == "user":
            source = next(source for source in included_sources if source.ref == item.ref)
            if item.text != source.text:
                raise DialogueError("INVALID_EVENT")

    retained_history = all_history[-policy.max_history_items :]
    omitted = all_history[: max(0, len(all_history) - policy.max_history_items)]
    entries = list(summary_entries)
    indexed_refs = {entry.quote.ref for entry in entries}
    for item in omitted:
        if item.role == "user" and item.ref not in indexed_refs:
            # An exact quote preserves the omitted user's source dependency. If
            # it exceeds a budget below, fail rather than silently lose it.
            entries.append(
                SummaryEntry(
                    quote=SourceQuote(ref=item.ref, start=0, end=len(item.text), text=item.text),
                    label="topic",
                )
            )
            indexed_refs.add(item.ref)
    for entry in entries:
        validate_quote(entry.quote, included_sources)
    payload = {
        "scope": scope,
        "purpose": "dialogue",
        "manifest_id": manifest.id,
        "manifest_version": manifest.version,
        "selection_refs": manifest.ordered_refs,
        "source_refs": refs,
        "sources": included_sources,
        "recent_history": retained_history,
        "summary_entries": tuple(entries),
        "asked_keys": _unique(asked_keys),
        "skipped_keys": _unique(skipped_keys),
        "context_revision": context_revision,
    }
    context_id = uuid5(scope.session_id, f"context:{canonical_digest(payload)}")
    try:
        context = ContextSnapshot(id=context_id, **payload)
    except ValidationError:
        raise DialogueError("INVALID_EVENT") from None
    return validate_context(context, policy)
