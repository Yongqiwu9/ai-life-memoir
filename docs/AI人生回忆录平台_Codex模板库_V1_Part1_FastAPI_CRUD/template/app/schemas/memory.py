from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MemoryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    memory_date: datetime | None = None
    emotion: str | None = Field(default=None, max_length=50)


class MemoryUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1)
    memory_date: datetime | None = None
    emotion: str | None = Field(default=None, max_length=50)


class MemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    content: str
    memory_date: datetime | None
    emotion: str | None
    created_at: datetime
    updated_at: datetime


class MemoryList(BaseModel):
    items: list[MemoryRead]
    page: int
    page_size: int
    total: int
