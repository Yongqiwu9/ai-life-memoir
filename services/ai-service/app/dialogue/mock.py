"""Deterministic synthetic replies, without keyword inference or model calls."""

from uuid import uuid5

from app.dialogue.contracts import (
    ContextSnapshot,
    GenerateEffect,
    Response,
    SourceQuote,
    SourceVersionRef,
    generation_binding,
)
from app.dialogue.provider import QUESTION_CATALOG, sourced_question


class DeterministicDialogueMock:
    """An explicitly configured fixture. Script entries are consumed once, without retries."""

    def __init__(
        self,
        *,
        outcome: str | None = None,
        question_key: str | None = None,
        topic_key: str = "reminiscence",
        text: str | None = None,
        basis_kind: str = "neutral",
        source_ref: SourceVersionRef | None = None,
        basis_quotes: tuple[SourceQuote, ...] | None = None,
        script: tuple[Response | Exception, ...] | None = None,
    ) -> None:
        self.outcome = outcome
        self.question_key = question_key
        self.topic_key = topic_key
        self.text = text
        self.basis_kind = basis_kind
        self.source_ref = source_ref
        self.basis_quotes = basis_quotes
        self.script = script
        self.calls = 0

    def generate_response(self, effect: GenerateEffect, context: ContextSnapshot) -> Response:
        self.calls += 1
        if self.script is not None:
            if self.calls > len(self.script):
                raise RuntimeError("OFFLINE_SCRIPT_EXHAUSTED")
            entry = self.script[self.calls - 1]
            if isinstance(entry, Exception):
                raise entry
            return entry

        binding = generation_binding(effect)
        binding["effect_id"] = effect.effect_id
        binding["response_id"] = uuid5(effect.request_id, "response")
        outcome = self.outcome
        if outcome is None:
            outcome = next(
                item for item in ("question", "ack", "no_reply") if item in effect.allowed_outcomes
            )
        if outcome == "no_reply":
            return Response(**binding, outcome="no_reply", basis_kind="none")
        if outcome == "ack":
            return Response(
                **binding,
                outcome="ack",
                text=self.text if self.text is not None else "嗯，我在听。",
                basis_kind="none",
            )

        key = self.question_key
        text = self.text
        if key is None:
            choice = next(
                (item for item in QUESTION_CATALOG if item[0] not in context.asked_keys), None
            )
            if choice is None:
                return Response(**binding, outcome="no_reply", basis_kind="none")
            key, default_text = choice
            if text is None:
                text = default_text
        elif text is None:
            text = next(
                (item[1] for item in QUESTION_CATALOG if item[0] == key),
                QUESTION_CATALOG[0][1],
            )

        quotes = self.basis_quotes or ()
        if self.basis_kind == "sourced":
            if not quotes:
                source = next(
                    (
                        item
                        for item in context.sources
                        if self.source_ref is None or item.ref == self.source_ref
                    ),
                    None,
                )
                if source is None:
                    raise RuntimeError("OFFLINE_SOURCE_UNAVAILABLE")
                quotes = (
                    SourceQuote(ref=source.ref, start=0, end=len(source.text), text=source.text),
                )
            if self.text is None:
                text = sourced_question("；".join(quote.text for quote in quotes))

        return Response(
            **binding,
            outcome=outcome,
            question_key=key,
            topic_key=self.topic_key,
            text=text,
            basis_kind=self.basis_kind,
            basis_quotes=quotes,
        )
