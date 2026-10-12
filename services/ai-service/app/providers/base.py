"""Synchronous provider boundary, restricted to synthetic offline execution."""

from typing import Protocol

from app.contracts import QuestionRequest, QuestionResult


class AIProvider(Protocol):
    def generate_question(self, context: QuestionRequest) -> QuestionResult: ...
