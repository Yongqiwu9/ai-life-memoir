import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import MessageRole, MessageSource


class InterviewMessageCreate(BaseModel):
    role: Literal["user"] = "user"
    source: Literal["text"] = "text"
    content: str = Field(min_length=1, max_length=10000)


class InterviewMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    role: MessageRole
    source: MessageSource
    transcript_segment_id: uuid.UUID | None
    content: str
    sequence: int
    created_at: datetime


class InterviewMessageList(BaseModel):
    items: list[InterviewMessageRead]
    total: int
