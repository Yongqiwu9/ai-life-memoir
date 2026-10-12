"""Offline wire adapters. Production processing and transport remain unavailable."""

import unicodedata
from typing import Protocol
from uuid import UUID

from app.core.exceptions import AppException
from app.schemas.interview_agent import QuestionRequest, QuestionResult

# Mirrored synthetic data, not an import from the independent AI application.
QUESTION_CATALOG = (
    ("opening", "您想从哪段回忆开始讲起？"),
    ("detail", "关于您刚才的回忆，您还想补充什么？"),
    ("feeling", "您愿意谈谈讲述这段回忆时的感受吗？"),
    ("continue", "接下来，您还想分享什么？"),
    ("pause", "您想继续这段回忆，还是换一个话题？"),
)


def normalize_question(text: str) -> str:
    return "".join(
        char.casefold()
        for char in unicodedata.normalize("NFKC", text)
        if not char.isspace() and not unicodedata.category(char).startswith("P")
    )


class InterviewAIClient(Protocol):
    provider_id: str

    def next_question(self, request: QuestionRequest) -> QuestionResult: ...


class ProcessingDecision(Protocol):
    def require(self, *, user_id: UUID, session_id: UUID, source_ids: list[UUID]) -> None: ...


class UnavailableProcessingDecision:
    def require(self, *, user_id: UUID, session_id: UUID, source_ids: list[UUID]) -> None:
        raise AppException(
            "Interview AI processing unavailable", code="POLICY_UNAVAILABLE", status_code=503
        )


class UnavailableInterviewClient:
    provider_id = "unavailable"

    def next_question(self, request: QuestionRequest) -> QuestionResult:
        raise AppException("Interview AI unavailable", code="AI_UNAVAILABLE", status_code=503)


class DeterministicMockClient:
    """Explicit synthetic-test injection; never enabled by a runtime dependency."""

    provider_id = "mock"

    def next_question(self, request: QuestionRequest) -> QuestionResult:
        keys = {item.question_key for item in request.asked_questions}
        texts = {normalize_question(item.text) for item in request.asked_questions}
        catalog = (
            QUESTION_CATALOG
            if request.context_text is not None
            else (QUESTION_CATALOG[0], QUESTION_CATALOG[3], QUESTION_CATALOG[4])
        )
        selected = next(
            (
                (key, text)
                for key, text in catalog
                if key not in keys and normalize_question(text) not in texts
            ),
            None,
        )
        follow_up = (
            request.context_text is not None
            and selected is not None
            and selected[0] in {"detail", "feeling"}
        )
        return QuestionResult(
            request_id=request.request_id,
            session_id=request.session_id,
            policy_version=request.policy_version,
            agent_version=request.agent_version,
            generation_epoch=request.generation_epoch,
            context_message_ids=request.context_message_ids,
            outcome="question" if selected else "no_question",
            question_key=selected[0] if selected else None,
            question=selected[1] if selected else None,
            question_basis=("follow_up" if follow_up else "neutral") if selected else None,
            basis_message_ids=request.context_message_ids if follow_up else (),
        )


def get_processing_decision() -> ProcessingDecision:
    return UnavailableProcessingDecision()


def get_interview_client() -> InterviewAIClient:
    return UnavailableInterviewClient()
