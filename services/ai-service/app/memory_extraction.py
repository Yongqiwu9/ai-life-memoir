"""Provider-neutral offline extraction, with immutable DTO and complete echo checks."""

from app.memory_contracts import MemoryExtractionRequest, MemoryExtractionResult
from app.providers.memory_base import MemoryProvider
from app.providers.memory_registry import get_memory_provider


class MemoryExtractionRunner:
    def __init__(self, provider: MemoryProvider | None = None):
        self.provider = get_memory_provider("mock") if provider is None else provider

    def extract(self, request: MemoryExtractionRequest) -> MemoryExtractionResult:
        context = MemoryExtractionRequest.model_validate(request)
        result = MemoryExtractionResult.model_validate(self.provider.extract(context))
        return result.validate_binding(context)


def extract_memories(
    request: MemoryExtractionRequest, provider: MemoryProvider | None = None
) -> MemoryExtractionResult:
    return MemoryExtractionRunner(provider).extract(request)
