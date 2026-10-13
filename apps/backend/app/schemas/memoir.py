import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MemoirSectionReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    memory_id: uuid.UUID
    memory_revision_id: uuid.UUID
    approval_proposal_id: uuid.UUID


class MemoirCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    title: str = Field(min_length=1, max_length=200, strict=True)
    sections: tuple[MemoirSectionReference, ...] = Field(min_length=1, max_length=100)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value):
        if not value.strip():
            raise ValueError("A nonblank title is required")
        return value

    @field_validator("sections", mode="before")
    @classmethod
    def sections_array(cls, value):
        if not isinstance(value, (list, tuple)):
            raise ValueError("An array is required")  # noqa: TRY004 -- Pydantic requires ValueError
        return value

    @field_validator("sections")
    @classmethod
    def unique_memories(cls, value):
        if len({item.memory_id for item in value}) != len(value):
            raise ValueError("Duplicate memory IDs")
        return value


class MemoirSectionRead(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: uuid.UUID
    memory_id: uuid.UUID
    position: int
    record_origin: Literal["legacy_snapshot", "approved_revision_snapshot"]
    memory_revision_id: uuid.UUID | None
    approval_proposal_id: uuid.UUID | None


class MemoirSectionContent(MemoirSectionRead):
    title: str
    content: str
    source_message_id: uuid.UUID


class MemoirRead(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: uuid.UUID
    family_member_id: uuid.UUID
    status: Literal["draft"]
    record_origin: Literal["legacy", "versioned"]
    created_at: datetime
    section_count: int = Field(ge=0)


class MemoirContent(MemoirRead):
    title: str
    sections: list[MemoirSectionContent]


class MemoirSectionList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[MemoirSectionRead]
    total: int
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
