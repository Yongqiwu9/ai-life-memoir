import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import TranscriptStatus


class TranscriptCreate(BaseModel):
    provider: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    language: str | None = Field(default=None, max_length=32)
    status: TranscriptStatus = TranscriptStatus.PENDING


class TranscriptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    audio_recording_id: uuid.UUID
    provider: str | None
    model: str | None
    language: str | None
    status: TranscriptStatus
    text: str | None
    duration_ms: int | None
    created_at: datetime
    updated_at: datetime


class TranscriptList(BaseModel):
    items: list[TranscriptRead]
    total: int
