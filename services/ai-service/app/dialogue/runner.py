"""Synthetic effect execution and callback envelopes, with no implicit provider or I/O."""

from uuid import uuid5

from pydantic import ValidationError

from app.dialogue.contracts import (
    ACK_TEXTS,
    GENERATION_BINDING_FIELDS,
    NEUTRAL_QUESTIONS,
    ContextSnapshot,
    DialogueError,
    DialogueState,
    Event,
    FailurePayload,
    GenerateEffect,
    ReadyPayload,
    Response,
    SourceQuote,
    canonical_digest,
    generation_binding,
    source_fingerprint,
)
from app.dialogue.provider import OfflineDialogueProvider, sourced_question


def _check_quote(quote: SourceQuote, context: ContextSnapshot) -> None:
    source = next((item for item in context.sources if item.ref == quote.ref), None)
    if (
        source is None
        or source.availability != "available"
        or quote.end > len(source.text)
        or source.text[quote.start : quote.end] != quote.text
    ):
        raise DialogueError("INVALID_RESPONSE")


def _checked_context(effect: GenerateEffect, value: ContextSnapshot) -> ContextSnapshot:
    try:
        context = ContextSnapshot.model_validate(value)
    except (ValidationError, TypeError, ValueError, AttributeError):
        raise DialogueError("INVALID_EVENT") from None
    if (
        context.purpose != "dialogue"
        or context.scope != effect.scope
        or context.id != effect.context_id
        or context.context_revision != effect.context_revision
        or context.manifest_id != effect.manifest_id
        or context.manifest_version != effect.manifest_version
        or effect.dependency_refs[: len(context.source_refs)] != context.source_refs
        or effect.effect_id != uuid5(effect.request_id, "generate")
    ):
        raise DialogueError("INVALID_EVENT")

    # The raw-source prefix is exact. Extra refs are transitive cancellation
    # dependencies of AI history, never a directory of additional readable text.
    if len(set(effect.dependency_refs)) != len(effect.dependency_refs) or (
        len(effect.dependency_refs) > len(context.source_refs)
        and not any(item.role == "assistant" for item in context.recent_history)
    ):
        raise DialogueError("INVALID_EVENT")
    for ref in effect.dependency_refs:
        scope = ref.source_scope
        if (
            scope.owner_user_id != context.scope.actor_user_id
            or scope.family_id != context.scope.family_id
            or scope.family_member_id != context.scope.family_member_id
        ):
            raise DialogueError("INVALID_EVENT")

    stable_ids = tuple((ref.kind, ref.version_id) for ref in context.source_refs)
    sequences = tuple(item.sequence for item in context.recent_history)
    if (
        len(set(stable_ids)) != len(stable_ids)
        or len(set(sequences)) != len(sequences)
        or sequences != tuple(sorted(sequences))
    ):
        raise DialogueError("INVALID_EVENT")

    # Inspect every scope/availability before reading any fixture body.
    for source in context.sources:
        scope = source.ref.source_scope
        if (
            scope.owner_user_id != context.scope.actor_user_id
            or scope.family_id != context.scope.family_id
            or scope.family_member_id != context.scope.family_member_id
        ):
            raise DialogueError("INVALID_EVENT")
        if source.availability != "available":
            raise DialogueError("SOURCE_UNAVAILABLE")
        selected = source.ref in context.selection_refs
        if not selected and (
            source.ref.kind != "message"
            or scope.origin_interview_id != context.scope.interview_id
            or scope.origin_session_id != context.scope.session_id
        ):
            raise DialogueError("INVALID_EVENT")

    for source in context.sources:
        if source.revision_fingerprint != source_fingerprint(source.text):
            raise DialogueError("INVALID_EVENT")
    for item in context.recent_history:
        if item.role == "user":
            source = next((entry for entry in context.sources if entry.ref == item.ref), None)
            if source is None or source.text != item.text:
                raise DialogueError("INVALID_EVENT")
    for summary in context.summary_entries:
        _check_quote(summary.quote, context)
    payload = {name: getattr(context, name) for name in type(context).model_fields if name != "id"}
    if context.id != uuid5(context.scope.session_id, f"context:{canonical_digest(payload)}"):
        raise DialogueError("INVALID_EVENT")
    return context


def validate_response(
    response: Response, effect: GenerateEffect, context: ContextSnapshot
) -> Response:
    """Validate all reservation echoes and content; exceptions never contain source text."""
    try:
        reservation = GenerateEffect.model_validate(effect)
        checked_context = _checked_context(reservation, context)
        result = Response.model_validate(response)
        if (
            any(
                getattr(result, name) != getattr(reservation, name)
                for name in GENERATION_BINDING_FIELDS
            )
            or result.effect_id != reservation.effect_id
            or reservation.effect_id != uuid5(reservation.request_id, "generate")
            or result.response_id != uuid5(reservation.request_id, "response")
            or result.outcome not in reservation.allowed_outcomes
        ):
            raise DialogueError("INVALID_RESPONSE")
        if result.outcome == "no_reply":
            return result
        if result.outcome == "ack":
            if result.text not in ACK_TEXTS:
                raise DialogueError("INVALID_RESPONSE")
            return result
        if result.basis_kind == "neutral":
            if result.text not in NEUTRAL_QUESTIONS:
                raise DialogueError("INVALID_RESPONSE")
        elif result.basis_kind == "sourced":
            for quote in result.basis_quotes:
                _check_quote(quote, checked_context)
            quoted_text = "；".join(quote.text for quote in result.basis_quotes)
            if result.text != sourced_question(quoted_text):
                raise DialogueError("INVALID_RESPONSE")
        else:
            raise DialogueError("INVALID_RESPONSE")
        if reservation.trigger == "auto" and result.question_key in checked_context.asked_keys:
            raise DialogueError("INVALID_RESPONSE")
        return result
    except (DialogueError, ValidationError, TypeError, ValueError, AttributeError):
        raise DialogueError("INVALID_RESPONSE") from None


def run_effect(
    effect: GenerateEffect,
    context: ContextSnapshot,
    provider: OfflineDialogueProvider | None = None,
) -> ReadyPayload | FailurePayload:
    """Consume one new effect once; the caller owns ordering and must not execute replays."""
    try:
        reservation = GenerateEffect.model_validate(effect)
    except (ValidationError, TypeError, ValueError, AttributeError):
        raise DialogueError("INVALID_EVENT") from None
    binding = generation_binding(reservation)
    try:
        checked_context = _checked_context(reservation, context)
    except DialogueError as error:
        return FailurePayload(**binding, error_code=error.code)
    if provider is None:
        return FailurePayload(**binding, error_code="INVALID_EVENT")
    try:
        result = provider.generate_response(reservation, checked_context)
    except ValidationError:
        return FailurePayload(**binding, error_code="INVALID_RESPONSE")
    except Exception:  # noqa: BLE001 -- untrusted provider errors must not expose their bodies
        return FailurePayload(**binding, error_code="PROVIDER_FAILED")
    try:
        validated = validate_response(result, reservation, checked_context)
    except DialogueError:
        return FailurePayload(**binding, error_code="INVALID_RESPONSE")
    return ReadyPayload(**binding, response=validated)


def envelope_callback(
    state: DialogueState, payload: ReadyPayload | FailurePayload, time_ms: int
) -> Event:
    """Wrap a bound result at the current sequence/version using explicit logical time."""
    try:
        current = DialogueState.model_validate(state)
        if isinstance(payload, ReadyPayload):
            callback = ReadyPayload.model_validate(payload)
        elif isinstance(payload, FailurePayload):
            callback = FailurePayload.model_validate(payload)
        else:
            raise DialogueError("INVALID_EVENT")
        if callback.scope != current.scope:
            raise DialogueError("INVALID_EVENT")
        sequence = current.last_seq + 1
        return Event(
            event_id=uuid5(callback.request_id, f"callback:{callback.kind}:{sequence}"),
            seq=sequence,
            time_ms=time_ms,
            scope=current.scope,
            expected_version=current.version,
            payload=callback,
        )
    except (DialogueError, ValidationError, TypeError, ValueError, AttributeError):
        raise DialogueError("INVALID_EVENT") from None
