"""Synchronous, synthetic-only Memory provider boundary."""

from typing import Protocol

from app.memory_contracts import MemoryExtractionRequest, MemoryExtractionResult


class MemoryProvider(Protocol):
    def extract(self, request: MemoryExtractionRequest) -> MemoryExtractionResult: ...
