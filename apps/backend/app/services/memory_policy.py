"""Body-free, source/purpose-specific receipts; no production consent adapter."""

from collections.abc import Mapping
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.exceptions import AppException

PURPOSES = frozenset({"recording", "transcription", "ai_analysis", "family_share/text_derived"})


def derive_required_purposes(
    source_type: str, *, inherited=(), ai_analysis: bool = False, family_shared: bool = False
) -> tuple[str, ...]:
    purposes = set(inherited)
    if source_type == "audio_transcript":
        purposes.update({"recording", "transcription"})
    elif source_type != "text":
        raise AppException("Invalid source", code="INVALID_SOURCE", status_code=422)
    if ai_analysis:
        purposes.add("ai_analysis")
    if family_shared:
        purposes.add("family_share/text_derived")
    if not purposes <= PURPOSES:
        raise AppException(
            "Memory processing unavailable", code="MEMORY_PROCESSING_UNAVAILABLE", status_code=503
        )
    return tuple(sorted(purposes))


class DecisionStamp(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    profile: Literal["offline_memory.v1"] = "offline_memory.v1"
    policy_version: Literal["synthetic-offline.v1"] = "synthetic-offline.v1"
    operation: str
    actor_user_id: UUID
    family_scope_id: UUID
    family_member_id: UUID
    source_scope_id: UUID
    source_generation: int = Field(ge=0, strict=True)
    required_purposes: tuple[str, ...]
    purpose_generations: dict[str, int]
    allow: bool = Field(strict=True)
    body_available: bool = Field(strict=True)
    restore_verified: bool = Field(strict=True)

    @field_validator("required_purposes", mode="before")
    @classmethod
    def strict_purposes(cls, value):
        if not isinstance(value, (list, tuple)) or any(type(item) is not str for item in value):
            raise ValueError("Invalid purpose set")
        if len(set(value)) != len(value) or not set(value) <= PURPOSES:
            raise ValueError("Invalid purpose set")
        return tuple(sorted(value))

    @field_validator("purpose_generations", mode="before")
    @classmethod
    def strict_generations(cls, value):
        if not isinstance(value, dict) or any(
            type(key) is not str or type(item) is not int or item < 0 for key, item in value.items()
        ):
            raise ValueError("Invalid purpose generations")
        return dict(value)

    @model_validator(mode="after")
    def generation_keys(self):
        if set(self.purpose_generations) != set(self.required_purposes):
            raise ValueError("Required purpose generations must match")
        return self

    def receipt(self) -> dict:
        return self.model_dump(mode="json", exclude={"allow", "body_available", "restore_verified"})

    def matches_epoch(self, previous: Mapping) -> bool:
        if not isinstance(previous, Mapping):
            return False
        try:
            prior = DecisionStamp.model_validate(
                {
                    **previous,
                    "allow": True,
                    "body_available": True,
                    "restore_verified": True,
                }
            ).receipt()
        except ValueError:
            return False
        current = self.receipt()
        return all(
            prior.get(name) == current[name]
            for name in (
                "profile",
                "policy_version",
                "family_scope_id",
                "family_member_id",
                "source_scope_id",
                "source_generation",
                "required_purposes",
                "purpose_generations",
            )
        )


class MemoryPolicy:
    """Unavailable by default. Override only with a trusted adapter or synthetic fixture."""

    def require(
        self,
        *,
        operation: str,
        user_id: UUID,
        family_scope_id: UUID,
        family_member_id: UUID,
        source_scope_id: UUID,
        required_purposes,
        previous_stamp: Mapping | None = None,
    ) -> DecisionStamp:
        raise AppException(
            "Memory processing unavailable", code="MEMORY_PROCESSING_UNAVAILABLE", status_code=503
        )


class SyntheticMemoryPolicy(MemoryPolicy):
    """Source-indexed explicit fixtures; missing/unknown sources are restricted."""

    def __init__(self, decisions: Mapping[UUID, DecisionStamp]):
        self.decisions = dict(decisions)

    def require(
        self,
        *,
        operation: str,
        user_id: UUID,
        family_scope_id: UUID,
        family_member_id: UUID,
        source_scope_id: UUID,
        required_purposes,
        previous_stamp: Mapping | None = None,
    ) -> DecisionStamp:
        stamp = self.decisions.get(source_scope_id)
        if stamp is None:
            raise AppException("Content restricted", code="CONTENT_RESTRICTED", status_code=403)
        stamp = DecisionStamp.model_validate(stamp)
        expected = tuple(sorted(set(required_purposes)))
        if (
            stamp.actor_user_id != user_id
            or stamp.family_scope_id != family_scope_id
            or stamp.family_member_id != family_member_id
            or stamp.source_scope_id != source_scope_id
            or not set(expected) <= set(stamp.required_purposes)
            or not stamp.allow
            or not stamp.body_available
            or not stamp.restore_verified
        ):
            raise AppException("Content restricted", code="CONTENT_RESTRICTED", status_code=403)
        result = stamp.model_copy(
            update={
                "operation": operation,
                "required_purposes": expected,
                "purpose_generations": {
                    purpose: stamp.purpose_generations[purpose] for purpose in expected
                },
            }
        )
        result = DecisionStamp.model_validate(result)
        if previous_stamp is not None and not result.matches_epoch(previous_stamp):
            raise AppException("Content restricted", code="CONTENT_RESTRICTED", status_code=403)
        return result


def get_memory_policy() -> MemoryPolicy:
    return MemoryPolicy()
