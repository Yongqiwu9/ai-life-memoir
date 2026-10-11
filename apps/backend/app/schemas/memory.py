import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class MemoryRead(MemoryFields):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    family_member_id: uuid.UUID
    source_message_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class MemoryList(BaseModel):
    items: list[MemoryRead]
    total: int
    page: int
    page_size: int
