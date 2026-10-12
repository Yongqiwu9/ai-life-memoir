"""Provider-neutral content generation, isolated from Backend permissions and storage."""

from app.contracts import QuestionRequest, QuestionResult
from app.providers.base import AIProvider
from app.providers.mock import QUESTION_CATALOG, normalize_question
from app.providers.registry import get_provider

__all__ = ["QUESTION_CATALOG", "InterviewAgentRunner", "next_question", "normalize_question"]


class InterviewAgentRunner:
    def __init__(self, provider: AIProvider | None = None):
        self.provider = get_provider("mock") if provider is None else provider

    def next_question(self, request: QuestionRequest) -> QuestionResult:
        context = QuestionRequest.model_validate(request)
        result = QuestionResult.model_validate(self.provider.generate_question(context))
        result.validate_binding(context)
        if result.outcome == "question" and (
            result.question_key in {question.question_key for question in context.asked_questions}
            or normalize_question(result.question)
            in {normalize_question(question.text) for question in context.asked_questions}
        ):
            raise ValueError("Provider repeated a previously asked question")
        return result


def next_question(request: QuestionRequest, provider: AIProvider | None = None) -> QuestionResult:
    return InterviewAgentRunner(provider).next_question(request)
