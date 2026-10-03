import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import SessionStatus


class InterviewSessionCreate(BaseModel):
    status: SessionStatus = SessionStatus.ACTIVE


class InterviewSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    interview_id: uuid.UUID
    status: SessionStatus
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime
    updated_at: datetime


class InterviewSessionList(BaseModel):
    items: list[InterviewSessionRead]
    total: int
