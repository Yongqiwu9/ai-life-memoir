import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TranscriptSegmentCreate(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    sequence: int | None = Field(default=None, ge=0)
    speaker: str | None = Field(default=None, max_length=200)
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def _validate_time_range(self) -> "TranscriptSegmentCreate":
        if self.start_ms is not None and self.end_ms is not None and self.end_ms < self.start_ms:
            raise ValueError("end_ms must be greater than or equal to start_ms")
        return self


class TranscriptSegmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    transcript_id: uuid.UUID
    sequence: int
    speaker: str | None
    text: str
    start_ms: int | None
    end_ms: int | None
    confidence: float | None
    created_at: datetime


class TranscriptSegmentList(BaseModel):
    items: list[TranscriptSegmentRead]
    total: int
