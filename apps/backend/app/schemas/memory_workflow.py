"""Strict offline Memory wire/request contracts and body-free metadata schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONTRACT_VERSION = "memory-extraction.v1"
MAX_CANDIDATES = 20


def _nonblank(value):
    if value is not None and not value.strip():
        raise ValueError("A nonblank string is required")
    return value


def _array(value):
    if not isinstance(value, (list, tuple)):
        raise ValueError("An array is required")  # noqa: TRY004 -- Pydantic requires ValueError
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


class RevisionPayload(StrictModel):
    title: str = Field(min_length=1, max_length=200, strict=True)
    content: str = Field(min_length=1, max_length=20000, strict=True)
    time_text: str | None = Field(max_length=200, strict=True)
    place: str | None = Field(max_length=200, strict=True)
    emotion: str | None = Field(max_length=100, strict=True)
    uncertainties: tuple[str, ...] = Field(max_length=20)

    _text_not_blank = field_validator("title", "content")(_nonblank)
    _uncertainties_array = field_validator("uncertainties", mode="before")(_array)

    @field_validator("uncertainties", mode="before")
    @classmethod
    def valid_uncertainties(cls, value):
        if not isinstance(value, (list, tuple)) or any(
            type(item) is not str or not 1 <= len(item) <= 1000 for item in value
        ):
            raise ValueError("Invalid uncertainty")
        return value


class MemoryExtractionRequest(StrictModel):
    request_id: UUID
    contract_version: Literal["memory-extraction.v1"] = CONTRACT_VERSION
    source_message_id: UUID
    source_text: str = Field(min_length=1, max_length=10000, strict=True)
    _source_not_blank = field_validator("source_text")(_nonblank)


class MemoryExtractionResult(StrictModel):
    request_id: UUID
    contract_version: Literal["memory-extraction.v1"]
    source_message_id: UUID
    candidates: tuple[RevisionPayload, ...] = Field(max_length=MAX_CANDIDATES)
    _candidates_array = field_validator("candidates", mode="before")(_array)

    def validate_binding(self, request: MemoryExtractionRequest):
        for name in ("request_id", "contract_version", "source_message_id"):
            if getattr(self, name) != getattr(request, name):
                raise ValueError("Provider result binding does not match request")
        return self


class ExtractionCreate(StrictModel):
    source_message_id: UUID


class VersionCommand(StrictModel):
    expected_version: int = Field(ge=0, strict=True)


class ManualCandidateCreate(StrictModel):
    source_message_id: UUID
    payload: RevisionPayload


class RevisionCreate(VersionCommand):
    parent_revision_id: UUID | None
    payload: RevisionPayload


class ProposalSubmit(VersionCommand):
    expected_target_version: int = Field(ge=0, strict=True)


class ProposalApprove(ProposalSubmit):
    pass


class ProposalReject(VersionCommand):
    decision_code: (
        Literal["unsupported_source", "inaccurate_content", "needs_revision", "not_selected"] | None
    ) = None


class MetadataModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ExtractionBatchRead(MetadataModel):
    id: UUID
    session_id: UUID
    family_member_id: UUID
    source_message_id: UUID
    state: Literal["pending", "completed", "failed", "discarded", "cancelled"]
    version: int = Field(ge=0)
    candidate_count: int | None = Field(default=None, ge=0, le=MAX_CANDIDATES)
    failure_code: str | None = None
    discard_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None = None
    candidate_ids: list[UUID] = Field(default_factory=list)


class CandidateRead(MetadataModel):
    id: UUID
    family_member_id: UUID
    source_message_id: UUID
    origin: Literal["extraction", "manual"]
    batch_id: UUID | None
    batch_ordinal: int | None
    version: int
    revision_counter: int
    promoted_memory_id: UUID | None
    created_at: datetime
    updated_at: datetime
    revision_ids: list[UUID] = Field(default_factory=list)
    proposal_ids: list[UUID] = Field(default_factory=list)


class RevisionRead(MetadataModel):
    id: UUID
    candidate_id: UUID | None
    memory_id: UUID | None
    source_message_id: UUID
    ordinal: int
    parent_revision_id: UUID | None
    origin_revision_id: UUID | None
    author_mode: Literal["mock_ai", "manual", "promotion"]
    body_state: Literal["present", "purged"]
    created_at: datetime
    updated_at: datetime


class ProposalRead(MetadataModel):
    id: UUID
    candidate_id: UUID | None
    memory_id: UUID | None
    input_revision_id: UUID
    base_version: int
    base_revision_id: UUID | None
    state: Literal["draft", "submitted", "approved", "rejected", "withdrawn", "stale", "purged"]
    version: int
    decision_code: str | None
    submitted_at: datetime | None
    decided_at: datetime | None
    result_memory_id: UUID | None
    result_memory_revision_id: UUID | None
    created_at: datetime
    updated_at: datetime


class RevisionContent(StrictModel):
    revision_id: UUID
    source_message_id: UUID
    payload: RevisionPayload


class MetadataList(StrictModel):
    items: list[ExtractionBatchRead | CandidateRead | RevisionRead | ProposalRead]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class ExtractionBatchList(StrictModel):
    items: list[ExtractionBatchRead]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class CandidateList(StrictModel):
    items: list[CandidateRead]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class RevisionList(StrictModel):
    items: list[RevisionRead]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class RevisionCreated(StrictModel):
    command_id: UUID | None = None
    candidate_id: UUID | None = None
    memory_id: UUID | None = None
    revision_id: UUID
    proposal_id: UUID
    version: int
    proposal_version: int

    @model_validator(mode="after")
    def target(self):
        if (self.candidate_id is None) == (self.memory_id is None):
            raise ValueError("Exactly one target is required")
        return self


class ExtractionCommandResult(StrictModel):
    """Body-free extraction result/replay, distinct from the full Batch metadata view."""

    command_id: UUID | None = None
    batch_id: UUID
    state: Literal["pending", "completed", "failed", "discarded", "cancelled"]
    version: int = Field(ge=0)
    candidate_count: int | None = Field(default=None, ge=0, le=MAX_CANDIDATES)
    failure_code: str | None = None
    discard_reason: str | None = None
    candidate_ids: list[UUID] = Field(default_factory=list)


class ProposalCommandResult(StrictModel):
    command_id: UUID | None = None
    proposal_id: UUID
    state: Literal["submitted", "approved", "rejected", "withdrawn", "stale"]
    version: int = Field(ge=0)
    target_version: int | None = Field(default=None, ge=0)
    memory_id: UUID | None = None
    memory_revision_id: UUID | None = None


class MemoirCreated(StrictModel):
    command_id: UUID | None = None
    memoir_id: UUID
    section_ids: list[UUID]
    record_origin: Literal["versioned"]


class ProcessingCommandResult(StrictModel):
    command_id: UUID
    state: Literal["processing"]


class PendingCommandStatus(StrictModel):
    command_id: UUID
    resource_kind: Literal["batch", "candidate", "proposal", "memory", "memoir"]
    resource_id: UUID
    state: Literal[
        "pending",
        "processing",
        "draft",
        "submitted",
        "approved",
        "rejected",
        "withdrawn",
        "stale",
        "purged",
        "completed",
        "failed",
        "discarded",
        "cancelled",
    ]
    version: int = Field(ge=0)


MemoryCommandResult = (
    ExtractionCommandResult
    | RevisionCreated
    | ProposalCommandResult
    | MemoirCreated
    | ProcessingCommandResult
    | PendingCommandStatus
)
