import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FamilyMemberCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class FamilyMemberUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)


class FamilyMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    family_id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime


class FamilyMemberList(BaseModel):
    items: list[FamilyMemberRead]
    page: int
    page_size: int
    total: int
