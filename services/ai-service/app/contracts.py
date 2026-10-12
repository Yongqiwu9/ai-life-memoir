from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONTRACT_VERSION = "interview-agent.v2"
LEGACY_CONTRACT_VERSION = "interview-agent.v1"
MOCK_POLICY_VERSION = "synthetic-mock.v1"
MAX_QUESTIONS = 24
MAX_TURNS = MAX_QUESTIONS


def _array(value):
    if not isinstance(value, (list, tuple)):
        raise ValueError("An array is required")  # noqa: TRY004 -- Pydantic wraps ValueError only
    return value


def _nonblank(value):
    if value is not None and not value.strip():
        raise ValueError("A nonblank string is required")
    return value


class AskedQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    message_id: UUID
    question_key: str = Field(min_length=1, max_length=100, strict=True)
    text: str = Field(min_length=1, max_length=120, strict=True)

    _text_not_blank = field_validator("question_key", "text")(_nonblank)


class QuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    contract_version: Literal["interview-agent.v2"] = CONTRACT_VERSION
    request_id: UUID
    session_id: UUID
    policy_version: Literal["synthetic-mock.v1"] = MOCK_POLICY_VERSION
    agent_version: int = Field(ge=0, strict=True)
    generation_epoch: int = Field(ge=0, strict=True)
    context_message_ids: tuple[UUID, ...] = Field(max_length=1)
    context_text: str | None = Field(default=None, min_length=1, max_length=10000, strict=True)
    asked_questions: tuple[AskedQuestion, ...] = Field(
        default_factory=tuple, max_length=MAX_QUESTIONS
    )

    _context_array = field_validator("context_message_ids", mode="before")(_array)
    _questions_array = field_validator("asked_questions", mode="before")(_array)
    _context_not_blank = field_validator("context_text")(_nonblank)

    @model_validator(mode="after")
    def validate_context(self):
        if bool(self.context_message_ids) != (self.context_text is not None):
            raise ValueError("Context identifiers and text must appear together")
        ids = [question.message_id for question in self.asked_questions]
        if len(set(ids)) != len(ids):
            raise ValueError("Asked question identifiers must be distinct")
        return self


class QuestionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    contract_version: Literal["interview-agent.v2"] = CONTRACT_VERSION
    request_id: UUID
    session_id: UUID
    policy_version: Literal["synthetic-mock.v1"] = MOCK_POLICY_VERSION
    agent_version: int = Field(ge=0, strict=True)
    generation_epoch: int = Field(ge=0, strict=True)
    context_message_ids: tuple[UUID, ...] = Field(max_length=1)
    outcome: Literal["question", "no_question"]
    question_key: str | None = Field(default=None, min_length=1, max_length=100, strict=True)
    question: str | None = Field(default=None, min_length=1, max_length=120, strict=True)
    question_basis: Literal["neutral", "follow_up"] | None = None
    basis_message_ids: tuple[UUID, ...] = Field(default_factory=tuple, max_length=1)

    _context_array = field_validator("context_message_ids", mode="before")(_array)
    _basis_array = field_validator("basis_message_ids", mode="before")(_array)
    _question_not_blank = field_validator("question_key", "question")(_nonblank)

    @model_validator(mode="after")
    def validate_outcome(self):
        if self.outcome == "no_question":
            if (
                any(
                    value is not None
                    for value in (self.question_key, self.question, self.question_basis)
                )
                or self.basis_message_ids
            ):
                raise ValueError("No-question results cannot contain a question or basis")
            return self
        if self.question_key is None or self.question is None or self.question_basis is None:
            raise ValueError("Question results require key, text and basis")
        if self.question_basis == "neutral" and self.basis_message_ids:
            raise ValueError("Neutral questions cannot contain a factual basis")
        if self.question_basis == "follow_up" and (
            len(self.context_message_ids) != 1 or self.basis_message_ids != self.context_message_ids
        ):
            raise ValueError("Follow-up basis must equal the original source")
        return self

    def validate_binding(self, request: QuestionRequest):
        for name in (
            "contract_version",
            "request_id",
            "session_id",
            "policy_version",
            "agent_version",
            "generation_epoch",
            "context_message_ids",
        ):
            if getattr(self, name) != getattr(request, name):
                raise ValueError("Provider result binding does not match the request")
        return self
