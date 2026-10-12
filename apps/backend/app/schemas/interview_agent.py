from datetime import UTC, datetime
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


ContractVersion = Literal["interview-agent.v1", "interview-agent.v2"]
AgentStatus = Literal["idle", "awaiting_answer", "listening", "paused", "ended"]
AgentAction = Literal["start", "answer", "skip", "request_question", "pause", "resume", "end"]
V1_STATUSES = frozenset(("idle", "awaiting_answer", "ended"))
V2_STATUSES = frozenset(("idle", "listening", "paused", "ended"))
V1_ACTIONS = frozenset(("start", "answer", "skip", "end"))
V2_ACTIONS = frozenset(("start", "request_question", "pause", "resume", "end"))


def _validate_status(version, status):
    allowed = V1_STATUSES if version == LEGACY_CONTRACT_VERSION else V2_STATUSES
    if status not in allowed:
        raise ValueError("Status does not match its contract version")


class AgentTurnCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["interview-agent.v2"]
    action: Literal["start", "request_question", "pause", "resume", "end"]
    expected_version: int = Field(ge=0, strict=True)


class AgentStateRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)

    session_id: UUID
    contract_version: ContractVersion
    status: AgentStatus
    version: int = Field(ge=0, strict=True)
    generation_epoch: int = Field(ge=0, strict=True)
    session_status: Literal["active", "completed", "cancelled"]
    pending_turn_id: UUID | None = None
    current_question_message_id: UUID | None = None

    @model_validator(mode="after")
    def validate_versioned_state(self):
        _validate_status(self.contract_version, self.status)
        return self


class AgentTurnRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)

    id: UUID
    session_id: UUID
    contract_version: ContractVersion
    action: AgentAction
    execution_status: Literal["pending", "completed", "failed", "discarded"]
    result_kind: Literal["control", "question", "no_question"] | None = None
    result_state_contract_version: ContractVersion | None = None
    resulting_version: int | None = Field(default=None, ge=0, strict=True)
    resulting_status: AgentStatus | None = None
    output_message_id: UUID | None = None
    failure_code: str | None = Field(default=None, min_length=1, max_length=64, strict=True)
    discard_reason: str | None = Field(default=None, min_length=1, max_length=64, strict=True)
    created_at: datetime
    finished_at: datetime | None = None

    @field_validator("created_at", "finished_at")
    @classmethod
    def normalize_utc(cls, value: datetime | None):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_versioned_result(self):
        actions = V1_ACTIONS if self.contract_version == LEGACY_CONTRACT_VERSION else V2_ACTIONS
        if self.action not in actions:
            raise ValueError("Action does not match its contract version")
        snapshots = (
            self.result_kind,
            self.result_state_contract_version,
            self.resulting_version,
            self.resulting_status,
        )
        if self.execution_status != "completed":
            if any(value is not None for value in (*snapshots, self.output_message_id)):
                raise ValueError("Unsuccessful turns cannot contain successful results")
            if self.action != "request_question" or self.contract_version != CONTRACT_VERSION:
                raise ValueError("Only v2 question turns have execution states")
            if self.execution_status == "pending":
                if any(
                    value is not None
                    for value in (self.failure_code, self.discard_reason, self.finished_at)
                ):
                    raise ValueError("Pending turns cannot contain terminal evidence")
            elif self.finished_at is None:
                raise ValueError("Terminal turns require a completion time")
            elif self.execution_status == "failed":
                if self.failure_code is None or self.discard_reason is not None:
                    raise ValueError("Failed turns require only a safe failure code")
            elif self.discard_reason is None or self.failure_code is not None:
                raise ValueError("Discarded turns require only a safe discard reason")
            return self
        if any(value is None for value in snapshots):
            raise ValueError("Completed turns require complete result snapshots")
        _validate_status(self.result_state_contract_version, self.resulting_status)
        if self.contract_version == CONTRACT_VERSION and self.finished_at is None:
            raise ValueError("V2 terminal turns require a completion time")
        if self.failure_code is not None or self.discard_reason is not None:
            raise ValueError("Completed turns cannot contain failure evidence")
        if self.result_kind != "question" and self.output_message_id is not None:
            raise ValueError("Only question results can contain an output")
        if self.contract_version == CONTRACT_VERSION:
            control = self.action != "request_question"
            if control != (self.result_kind == "control"):
                raise ValueError("Action and result kind do not match")
            if self.result_state_contract_version != CONTRACT_VERSION and self.action != "end":
                raise ValueError("Only explicit end may target a legacy state")
            if (
                self.result_state_contract_version == LEGACY_CONTRACT_VERSION
                and self.resulting_status != "ended"
            ):
                raise ValueError("Explicit legacy end must preserve an ended snapshot")
        elif self.result_state_contract_version != LEGACY_CONTRACT_VERSION:
            raise ValueError("Legacy results must preserve their state contract")
        return self
