"""Independent AI Service Memory wire contracts; Backend has an audited mirror."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

CONTRACT_VERSION = "memory-extraction.v1"
MAX_CANDIDATES = 20


def _nonblank(value):
    if value is not None and not value.strip():
        raise ValueError("A nonblank string is required")
    return value


def _array(value):
    if not isinstance(value, (list, tuple)):
        raise ValueError("An array is required")  # noqa: TRY004 -- Pydantic requires ValueError
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


class RevisionPayload(StrictModel):
    title: str = Field(min_length=1, max_length=200, strict=True)
    content: str = Field(min_length=1, max_length=20000, strict=True)
    time_text: str | None = Field(max_length=200, strict=True)
    place: str | None = Field(max_length=200, strict=True)
    emotion: str | None = Field(max_length=100, strict=True)
    uncertainties: tuple[str, ...] = Field(max_length=20)

    _text_not_blank = field_validator("title", "content")(_nonblank)
    _uncertainties_array = field_validator("uncertainties", mode="before")(_array)

    @field_validator("uncertainties", mode="before")
    @classmethod
    def valid_uncertainties(cls, value):
        if not isinstance(value, (list, tuple)) or any(
            type(item) is not str or not 1 <= len(item) <= 1000 for item in value
        ):
            raise ValueError("Invalid uncertainty")
        return value


class MemoryExtractionRequest(StrictModel):
    request_id: UUID
    contract_version: Literal["memory-extraction.v1"] = CONTRACT_VERSION
    source_message_id: UUID
    source_text: str = Field(min_length=1, max_length=10000, strict=True)
    _source_not_blank = field_validator("source_text")(_nonblank)


class MemoryExtractionResult(StrictModel):
    request_id: UUID
    contract_version: Literal["memory-extraction.v1"]
    source_message_id: UUID
    candidates: tuple[RevisionPayload, ...] = Field(max_length=MAX_CANDIDATES)
    _candidates_array = field_validator("candidates", mode="before")(_array)

    def validate_binding(self, request: MemoryExtractionRequest):
        for name in ("request_id", "contract_version", "source_message_id"):
            if getattr(self, name) != getattr(request, name):
                raise ValueError("Provider result binding does not match request")
        return self
