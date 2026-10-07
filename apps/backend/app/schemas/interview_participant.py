import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class ParticipantProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    roles: Literal["speaker"] = "speaker"
    family_member_id: uuid.UUID | None = None


class ParticipantConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verification_proof: SecretStr = Field(repr=False, min_length=1, max_length=4096)
    adult_autonomous_decision: Literal[True]
    expected_version: Annotated[int, Field(gt=0)]


class ParticipantInactivate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: Annotated[int, Field(gt=0)]


class ParticipantRead(BaseModel):
    """Rights-safe view: excludes archive linkage and verification evidence."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    roles: Literal["speaker"]
    state: Literal["proposed", "verified", "inactive", "disputed"]
    eligibility_state: Literal["unknown", "eligible", "ineligible"]
    verified_at: datetime | None
    adult_declaration_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime

    _normalize = field_validator("verified_at", "adult_declaration_at", "created_at", "updated_at")(
        _utc
    )
