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
