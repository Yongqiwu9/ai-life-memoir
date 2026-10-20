"""Exact checkpoint partition and pinned context loading, with pre-body dependency gates."""

import copy
import json
from types import SimpleNamespace
from uuid import UUID, uuid5

from sqlalchemy import select

from app.crud import dialogue as crud
from app.models.dialogue_runtime import AgentCheckpoint, AgentContext, AgentDependency
from app.schemas import dialogue as c
from app.services.dialogue_policy import error


def decode(model, value):
    return model.model_validate_json(json.dumps(value, ensure_ascii=False))


def split(state: c.DialogueState):
    metadata = state.model_dump(mode="json")
    sensitive = {"questions": {}, "responses": {}}
    for receipt in metadata["question_receipts"]:
        sensitive["questions"][receipt["response_id"]] = receipt.pop("normalized_text")
    for slot in ("ready_response", "active_response"):
        response = metadata[slot]
        if response is not None:
            sensitive["responses"][slot] = {
                "response_id": response["response_id"],
                "text": response.pop("text"),
                "quotes": [quote.pop("text") for quote in response["basis_quotes"]],
            }
    return metadata, sensitive


def merge(metadata, sensitive):
    value = copy.deepcopy(metadata)
    leaves = copy.deepcopy(sensitive)
    try:
        if set(leaves) != {"questions", "responses"}:
            raise ValueError("shape")
        for receipt in value["question_receipts"]:
            receipt["normalized_text"] = leaves["questions"].pop(receipt["response_id"])
        for slot in ("ready_response", "active_response"):
            response = value[slot]
            if response is not None:
                item = leaves["responses"].pop(slot)
                if (
                    set(item) != {"response_id", "text", "quotes"}
                    or item["response_id"] != response["response_id"]
                ):
                    raise ValueError("identity")
                response["text"] = item["text"]
                if len(item["quotes"]) != len(response["basis_quotes"]):
                    raise ValueError("quotes")
                for quote, body in zip(response["basis_quotes"], item["quotes"], strict=True):
                    quote["text"] = body
        if leaves["questions"] or leaves["responses"]:
            raise ValueError("extra")
        return decode(c.DialogueState, value)
    except Exception:  # noqa: BLE001 - leaves can contain source text
        raise error("DIALOGUE_CHECKPOINT_UNAVAILABLE") from None


def source_gate(db, actor, session_id, runtime):
    """No Message.content or checkpoint sensitive column is selected in this function."""
    runtime.require(actor, session_id)
    sources = crud.sources(db, session_id)
    for source in sources:
        item = crud.message_metadata(db, session_id, source.stable_message_id)
        if (
            source.availability != "available"
            or source.live_message_id is None
            or item is None
            or source.live_message_id != source.stable_message_id
            or item.role != "user"
            or item.source != "text"
            or item.sequence != source.message_sequence
        ):
            raise error("SOURCE_UNAVAILABLE")
    # References must resolve even when a source binding has been damaged/removed.
    edges = list(
        db.scalars(
            select(AgentDependency.source_message_id).where(
                AgentDependency.session_id == session_id
            )
        )
    )
    if not set(edges).issubset({row.stable_message_id for row in sources}):
        raise error("SOURCE_UNAVAILABLE")
    return sources


def load(db, actor, envelope, runtime):
    sources = source_gate(db, actor, envelope.session_id, runtime)
    checkpoint = crud.checkpoint(db, envelope.session_id)
    if checkpoint is None or checkpoint.content_status != "live":
        raise error("DIALOGUE_CHECKPOINT_UNAVAILABLE")
    metadata = checkpoint.metadata_json
    if (
        metadata.get("scope", {}).get("actor_user_id") != str(actor)
        or metadata.get("scope", {}).get("session_id") != str(envelope.session_id)
        or c.canonical_digest(metadata) != checkpoint.metadata_digest
        or metadata.get("version") != checkpoint.core_version
        or metadata.get("epoch") != checkpoint.core_epoch
        or metadata.get("last_seq") != checkpoint.last_seq
        or metadata.get("context_revision") != checkpoint.context_revision
        or checkpoint.checkpoint_version > envelope.persistence_version
    ):
        raise error("DIALOGUE_CHECKPOINT_UNAVAILABLE")
    ids = {row.stable_message_id for row in sources}
    for receipt in metadata.get("known_source_revisions", []):
        if UUID(receipt["ref"]["entity_id"]) not in ids:
            raise error("SOURCE_UNAVAILABLE")
    leaves = crud.sensitive(db, envelope.session_id)
    state = merge(metadata, leaves)
    runtime.integrity.verify(
        state.model_dump(mode="json"),
        bytes.fromhex(checkpoint.checkpoint_digest),
        checkpoint.integrity_key_id,
    )
    return state


def save(db, envelope, state, runtime):
    metadata, sensitive = split(state)
    row = crud.checkpoint(db, envelope.session_id)
    if row is not None and row.content_status != "live":
        raise error("DIALOGUE_CHECKPOINT_UNAVAILABLE")
    if row is None:
        row = AgentCheckpoint(session_id=envelope.session_id)
        db.add(row)
    row.checkpoint_version = envelope.persistence_version
    row.core_version = state.version
    row.core_epoch = state.epoch
    row.last_seq = state.last_seq
    row.context_revision = state.context_revision
    row.format_version = c.CONTRACT_VERSION
    row.metadata_json = metadata
    row.sensitive_json = sensitive
    row.metadata_digest = c.canonical_digest(metadata)
    row.integrity_key_id = runtime.integrity.current
    row.checkpoint_digest = runtime.integrity.sign(state.model_dump(mode="json")).hex()
    row.content_status = "live"
    envelope.version = state.version
    envelope.generation_epoch = state.epoch
    envelope.last_applied_event_seq = state.last_seq
    envelope.current_context_revision = state.context_revision
    db.flush()
    refs = list(state.context_source_refs)
    for effect in state.known_requests:
        refs.extend(effect.dependency_refs)
    crud.replace_checkpoint_edges(db, envelope.session_id, refs)


def context_descriptor(context):
    history = [
        {k: v for k, v in item.model_dump(mode="json").items() if k != "text"}
        for item in context.recent_history
    ]
    slices = [
        {
            "label": item.label,
            **{k: v for k, v in item.quote.model_dump(mode="json").items() if k != "text"},
        }
        for item in context.summary_entries
    ]
    sources = [
        {
            "ref": item.ref.model_dump(mode="json"),
            "availability": item.availability,
            "revision_fingerprint": item.revision_fingerprint,
        }
        for item in context.sources
    ]
    values = {
        "context_id": context.id,
        "manifest_id": context.manifest_id,
        "manifest_version": context.manifest_version,
        "purpose": "dialogue",
        "context_digest": c.canonical_digest(context),
        "source_order": sources,
        "history_order": history,
        "quote_slices": slices,
        "asked_keys": list(context.asked_keys),
        "skipped_keys": list(context.skipped_keys),
    }
    return {
        **values,
        "context_id": str(context.id),
        "manifest_id": str(context.manifest_id),
        "revision": context.context_revision,
    }


def pin_context(db, context):
    row = db.get(AgentContext, (context.scope.session_id, context.context_revision))
    values = context_descriptor(context)
    values.pop("revision")
    values["context_id"] = UUID(values["context_id"])
    values["manifest_id"] = UUID(values["manifest_id"])
    if row is not None:
        if any(getattr(row, k) != v for k, v in values.items()):
            raise error("DIALOGUE_CONTEXT_CONFLICT")
        return
    db.add(
        AgentContext(
            session_id=context.scope.session_id, revision=context.context_revision, **values
        )
    )
    db.flush()
    for ref in context.source_refs:
        db.add(
            AgentDependency(
                session_id=context.scope.session_id,
                source_message_id=ref.entity_id,
                owner_kind="context",
                context_revision=context.context_revision,
            )
        )


def restore_context(db, actor, scope, revision, runtime, *, pinned=None):
    bindings = {
        row.stable_message_id: row for row in source_gate(db, actor, scope.session_id, runtime)
    }
    row = (
        db.get(AgentContext, (scope.session_id, revision))
        if pinned is None
        else SimpleNamespace(**pinned)
    )
    if pinned is not None:
        row.context_id = UUID(row.context_id)
        row.manifest_id = UUID(row.manifest_id)
        if row.revision != revision:
            raise error("DIALOGUE_CONTEXT_UNAVAILABLE")
    if row is None:
        raise error("DIALOGUE_CONTEXT_UNAVAILABLE")
    sources = []
    for entry in row.source_order:
        ref = decode(c.SourceVersionRef, entry["ref"])
        binding = bindings.get(ref.entity_id)
        if (
            binding is None
            or ref.source_scope.owner_user_id != actor
            or ref.source_scope.origin_session_id != scope.session_id
        ):
            raise error("SOURCE_UNAVAILABLE")
        body = crud.message_body(db, scope.session_id, ref.entity_id)
        if (
            body is None
            or c.source_fingerprint(body) != binding.fingerprint
            or binding.fingerprint != entry["revision_fingerprint"]
        ):
            raise error("SOURCE_UNAVAILABLE")
        sources.append(
            c.FixtureSource(
                ref=ref,
                text=body,
                availability="available",
                revision_fingerprint=binding.fingerprint,
            )
        )
    by_ref = {source.ref: source for source in sources}
    effects = crud.effects(db, scope.session_id)
    history = []
    for entry in row.history_order:
        item = dict(entry)
        if entry["role"] == "user":
            source = by_ref.get(decode(c.SourceVersionRef, entry["ref"]))
            if source is None:
                raise error("SOURCE_UNAVAILABLE")
            body = source.text
        else:
            output = next(
                (
                    x
                    for x in effects
                    if x.kind == "deliver" and str(x.response_id) == entry["response_id"]
                ),
                None,
            )
            if output is None or output.output_message_id is None:
                raise error("SOURCE_UNAVAILABLE")
            body = crud.message_body(db, scope.session_id, output.output_message_id)
            if body is None or c.source_fingerprint(body) != output.binding_json.get(
                "output_fingerprint"
            ):
                raise error("SOURCE_UNAVAILABLE")
        item["text"] = body
        history.append(decode(c.HistoryItem, item))
    summaries = []
    for entry in row.quote_slices:
        ref = decode(c.SourceVersionRef, entry["ref"])
        source = by_ref.get(ref)
        if source is None:
            raise error("SOURCE_UNAVAILABLE")
        summaries.append(
            c.SummaryEntry(
                label=entry["label"],
                quote=c.SourceQuote(
                    ref=ref,
                    start=entry["start"],
                    end=entry["end"],
                    text=source.text[entry["start"] : entry["end"]],
                ),
            )
        )
    context = context_value(
        scope,
        row.revision,
        row.manifest_id,
        row.manifest_version,
        sources,
        history,
        summaries,
        row.asked_keys,
        row.skipped_keys,
    )
    if context.id != row.context_id or c.canonical_digest(context) != row.context_digest:
        raise error("DIALOGUE_CONTEXT_UNAVAILABLE")
    return context


def context_value(
    scope, revision, manifest_id, manifest_version, sources, history, summaries, asked, skipped
):
    values = {
        "scope": scope,
        "purpose": "dialogue",
        "context_revision": revision,
        "manifest_id": manifest_id,
        "manifest_version": manifest_version,
        "selection_refs": (),
        "source_refs": tuple(x.ref for x in sources),
        "sources": tuple(sources),
        "recent_history": tuple(history),
        "summary_entries": tuple(summaries),
        "asked_keys": tuple(asked),
        "skipped_keys": tuple(skipped),
    }
    return c.ContextSnapshot(
        id=uuid5(scope.session_id, "context:" + c.canonical_digest(values)), **values
    )
