"""Explicit injection boundary for synthetic, in-memory dialogue fixtures only."""

from typing import Protocol

from app.dialogue.contracts import (
    NEUTRAL_QUESTIONS,
    ContextSnapshot,
    GenerateEffect,
    Response,
)

QUESTION_CATALOG = tuple(
    (f"neutral-{index + 1}", text) for index, text in enumerate(NEUTRAL_QUESTIONS)
)


def sourced_question(quote_text: str) -> str:
    """Keep the exact speaker wording, including negation and uncertainty."""
    return f"关于您刚才说的“{quote_text}”，您愿意继续说说吗？"


class OfflineDialogueProvider(Protocol):
    """A synchronous fixture; no discovery, credentials or transport are supplied here."""

    def generate_response(self, effect: GenerateEffect, context: ContextSnapshot) -> Response: ...
