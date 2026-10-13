import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.memory_workflow import RevisionPayload


class MemoryFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=20000)
    time_text: str | None = Field(default=None, max_length=200)
    place: str | None = Field(default=None, max_length=200)
    emotion: str | None = Field(default=None, max_length=100)


class MemoryCreate(MemoryFields):
    source_message_id: uuid.UUID


class MemoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1, max_length=20000)
    time_text: str | None = Field(default=None, max_length=200)
    place: str | None = Field(default=None, max_length=200)
    emotion: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def required_content(self) -> "MemoryUpdate":
        for name in ("title", "content"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class MemoryMetadata(BaseModel):
    """Safe list/header fields; legacy and current payloads are not serialized."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: uuid.UUID
    family_member_id: uuid.UUID
    source_message_id: uuid.UUID
    record_origin: Literal["legacy", "versioned"]
    version: int
    revision_counter: int
    origin_candidate_id: uuid.UUID | None
    current_revision_id: uuid.UUID | None
    current_approval_proposal_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class MemoryRead(MemoryMetadata):
    current_content: RevisionPayload | None = None
    approval_state: str = "unapproved"


class LegacyMemorySnapshot(MemoryFields):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    id: uuid.UUID
    source_message_id: uuid.UUID
    approved: Literal[False] = False


class MemoryList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[MemoryMetadata]
    total: int
    page: int
    page_size: int
