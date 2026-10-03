import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FamilyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class FamilyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)


class FamilyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime


class FamilyList(BaseModel):
    items: list[FamilyRead]
    page: int
    page_size: int
    total: int
