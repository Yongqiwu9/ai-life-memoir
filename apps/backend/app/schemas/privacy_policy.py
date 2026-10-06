"""Explicit seconds, never implicit production retention defaults."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    create_model,
    model_validator,
)


class Duration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    seconds: Annotated[StrictInt, Field(gt=0)]


class PolicyParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sanitization_review_window: Duration
    sanitization_retry_limit: Annotated[StrictInt, Field(ge=0)]
    online_deletion_deadline: Duration
    third_party_deletion_deadline: Duration
    backup_retention_window: Duration
    object_version_retention_window: Duration
    database_recovery_retention_window: Duration
    withdrawal_quarantine_retention: Duration
    deletion_ledger_retention: Duration
    sanitization_evidence_retention: Duration
    invitation_window: Duration
    auth_challenge_window: Duration
    rights_token_window: Duration
    high_risk_reverification_window: Duration
    late_job_window: Duration

    @model_validator(mode="after")
    def check_coverage(self):
        if self.sanitization_review_window.seconds > self.online_deletion_deadline.seconds:
            raise ValueError("Sanitization cannot extend the online deletion deadline")
        recovery = (
            self.backup_retention_window,
            self.object_version_retention_window,
            self.database_recovery_retention_window,
            self.late_job_window,
        )
        if self.deletion_ledger_retention.seconds < max(item.seconds for item in recovery):
            raise ValueError("Ledger must cover all recovery and late-job windows")
        return self


DraftPolicyParameters = create_model(
    "DraftPolicyParameters",
    __config__=ConfigDict(extra="forbid"),
    **{
        name: (field.rebuild_annotation() | None, None)
        for name, field in PolicyParameters.model_fields.items()
    },
)


class CapabilityEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    verified: StrictBool
    evidence_ref: UUID


class PolicyCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    capture: CapabilityEvidence
    consent: CapabilityEvidence
    source_restore: CapabilityEvidence
    sanitization_publish: CapabilityEvidence
    external_processing: CapabilityEvidence

    @model_validator(mode="after")
    def check_verified(self):
        if not all(getattr(self, name).verified for name in type(self).model_fields):
            raise ValueError("Active policy requires verified capabilities")
        return self


class PolicyNotices(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    recording: Annotated[str, Field(min_length=1)]
    transcription: Annotated[str, Field(min_length=1)]
    ai_analysis: Annotated[str, Field(min_length=1)]
    family_share: Annotated[str, Field(min_length=1)]
    retention: Annotated[str, Field(min_length=1)]


ProcessingCapability = Literal[
    "capture", "consent", "source_restore", "sanitization_publish", "external_processing"
]
PrivacySafetyAction = Literal["withdrawal", "deletion"]
