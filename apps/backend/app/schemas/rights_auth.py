import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    StrictInt,
    TypeAdapter,
    model_validator,
)

from app.schemas.privacy_policy import Duration


class RightsAuthConfiguration(BaseModel):
    """Explicit provider configuration, independent of an active processing policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    challenge_ttl: Duration
    token_ttl: Duration
    attempt_limit: Annotated[StrictInt, Field(gt=0)]


class ChallengeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["email", "phone"]
    channel: SecretStr = Field(repr=False, max_length=320)
    context: Literal["rights_auth"] = "rights_auth"

    @model_validator(mode="after")
    def normalize_channel(self):
        raw = self.channel.get_secret_value().strip()
        try:
            if self.kind == "email":
                value = str(TypeAdapter(EmailStr).validate_python(raw)).lower()
            elif re.fullmatch(r"\+[1-9][0-9]{7,14}", raw):
                value = raw
            else:
                raise ValueError()
        except ValueError:
            raise ValueError("Invalid contact format") from None
        self.channel = SecretStr(value)
        return self


class ChallengeVerify(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: SecretStr = Field(repr=False, min_length=1, max_length=128)


class ChallengeReceipt(BaseModel):
    id: UUID
    status: Literal["accepted"] = "accepted"


class RightsMe(BaseModel):
    id: UUID
    principal_kind: Literal["account", "rights_only"]
    authentication: Literal["rights"] = "rights"
    capabilities: list[Literal["rights:identity"]]


class UserContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    kind: Literal["email", "phone"]
    state: Literal["pending", "verified", "revoked", "legacy_unverified"]
