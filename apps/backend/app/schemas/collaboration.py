import re
import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    TypeAdapter,
    field_validator,
    model_validator,
)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class InvitationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient_kind: Literal["email", "phone"]
    recipient: SecretStr = Field(repr=False, max_length=320)

    @model_validator(mode="after")
    def normalize_recipient(self):
        raw = self.recipient.get_secret_value().strip()
        try:
            if self.recipient_kind == "email":
                value = str(TypeAdapter(EmailStr).validate_python(raw)).lower()
            elif re.fullmatch(r"\+[1-9][0-9]{7,14}", raw):
                value = raw
            else:
                raise ValueError()
        except ValueError:
            raise ValueError("Invalid recipient format") from None
        self.recipient = SecretStr(value)
        return self


class InvitationTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: Annotated[int, Field(gt=0)]


class InvitationAccept(InvitationTransition):
    invitation_token: SecretStr = Field(repr=False, min_length=1, max_length=512)
    verification_proof: SecretStr = Field(repr=False, min_length=1, max_length=4096)


class InvitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    family_id: uuid.UUID
    requested_by_user_id: uuid.UUID
    recipient_user_id: uuid.UUID | None
    approved_by_user_id: uuid.UUID | None
    state: Literal[
        "pending_owner", "approved", "accepted", "rejected", "cancelled", "revoked", "expired"
    ]
    version: int
    approved_at: datetime | None
    accepted_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime

    _normalize_datetimes = field_validator(
        "approved_at", "accepted_at", "expires_at", "created_at", "updated_at"
    )(_utc)


class MembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    family_id: uuid.UUID
    user_id: uuid.UUID
    role: Literal["collaborator"]
    state: Literal["active", "revoked", "left"]
    generation: int
    joined_at: datetime
    ended_at: datetime | None
    created_at: datetime
    updated_at: datetime

    _normalize_datetimes = field_validator("joined_at", "ended_at", "created_at", "updated_at")(
        _utc
    )


class MembershipList(BaseModel):
    items: list[MembershipRead]
    page: int
    page_size: int
    total: int


class IdentityVerificationChallengeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_kind: Literal["invitation_acceptance"]
    context_id: uuid.UUID
    invitation_token: SecretStr = Field(repr=False, min_length=1, max_length=512)


class IdentityVerificationChallengeVerify(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: SecretStr = Field(repr=False, min_length=1, max_length=128)


class IdentityVerificationReceipt(BaseModel):
    id: uuid.UUID
    status: Literal["accepted"] = "accepted"


class VerificationProofResponse(BaseModel):
    verification_proof: str
    token_type: Literal["verification_proof"] = "verification_proof"


ExpectedGeneration = Annotated[int, Field(gt=0)]
