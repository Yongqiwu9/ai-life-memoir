import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AudioStatus


class AudioRecordingCreate(BaseModel):
    original_filename: str | None = Field(default=None, max_length=255)
    mime_type: str | None = Field(default=None, max_length=100)
    size_bytes: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    status: AudioStatus = AudioStatus.PENDING


class AudioRecordingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    storage_key: str | None
    original_filename: str | None
    mime_type: str | None
    size_bytes: int | None
    duration_ms: int | None
    status: AudioStatus
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AudioRecordingList(BaseModel):
    items: list[AudioRecordingRead]
    total: int
