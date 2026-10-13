"""Offline wire mirror, isolated from the independent AI application's app package."""

from typing import Protocol

from app.core.exceptions import AppException
from app.schemas.memory_workflow import (
    MemoryExtractionRequest,
    MemoryExtractionResult,
    RevisionPayload,
)


class MemoryAIClient(Protocol):
    provider_id: str

    def extract(self, request: MemoryExtractionRequest) -> MemoryExtractionResult: ...


def require_offline_provider(client: MemoryAIClient) -> str:
    """Server-only V1 allowlist; no dynamic import, fallback, or transport."""
    try:
        provider_id = client.provider_id
        if type(provider_id) is str and provider_id == "mock" and callable(client.extract):
            return provider_id
    except Exception:  # noqa: BLE001, S110 -- never log potentially private adapter exceptions.
        pass
    raise AppException(
        "Memory AI unavailable", code="MEMORY_PROCESSING_UNAVAILABLE", status_code=503
    ) from None


class UnavailableMemoryClient:
    provider_id = "unavailable"

    def extract(self, request: MemoryExtractionRequest) -> MemoryExtractionResult:
        raise AppException(
            "Memory AI unavailable", code="MEMORY_PROCESSING_UNAVAILABLE", status_code=503
        )


class DeterministicMockMemoryClient:
    """Fixture-only synthetic echo; does not claim fact extraction or model quality."""

    provider_id = "mock"

    def extract(self, request: MemoryExtractionRequest) -> MemoryExtractionResult:
        request = MemoryExtractionRequest.model_validate(request)
        return MemoryExtractionResult(
            request_id=request.request_id,
            contract_version=request.contract_version,
            source_message_id=request.source_message_id,
            candidates=(
                RevisionPayload(
                    title="合成回忆片段",
                    content=request.source_text,
                    time_text=None,
                    place=None,
                    emotion=None,
                    uncertainties=(),
                ),
            ),
        ).validate_binding(request)


def get_memory_client() -> MemoryAIClient:
    return UnavailableMemoryClient()
