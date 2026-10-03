from enum import StrEnum


class InterviewStatus(StrEnum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class InterviewType(StrEnum):
    LIFE_STORY = "life_story"
    FAMILY_HISTORY = "family_history"
    CHILDHOOD = "childhood"
    CAREER = "career"
    RELATIONSHIP = "relationship"
    OTHER = "other"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class MessageRole(StrEnum):
    ASSISTANT = "assistant"
    USER = "user"
    SYSTEM = "system"


class MessageSource(StrEnum):
    TEXT = "text"
    AUDIO_TRANSCRIPT = "audio_transcript"
    AI_GENERATED = "ai_generated"
    SYSTEM = "system"


class AudioStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TranscriptStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
