import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MemoirCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    memory_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)

    @field_validator("memory_ids")
    @classmethod
    def unique_memories(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(value)) != len(value):
            raise ValueError("Duplicate memory IDs")
        return value


class MemoirSectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    memory_id: uuid.UUID
    position: int
    title: str
    content: str


class MemoirRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    family_member_id: uuid.UUID
    title: str
    status: Literal["draft"]
    created_at: datetime
    sections: list[MemoirSectionRead]


class MemoirSectionList(BaseModel):
    items: list[MemoirSectionRead]
    total: int
