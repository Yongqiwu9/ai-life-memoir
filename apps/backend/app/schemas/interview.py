import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import InterviewStatus, InterviewType


class InterviewCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    type: InterviewType = InterviewType.OTHER


class InterviewUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: InterviewStatus | None = None
    type: InterviewType | None = None


class InterviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    family_member_id: uuid.UUID
    title: str
    status: InterviewStatus
    type: InterviewType
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class InterviewList(BaseModel):
    items: list[InterviewRead]
    page: int
    page_size: int
    total: int
