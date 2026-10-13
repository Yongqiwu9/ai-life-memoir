"""Deterministic synthetic echo; no claim of genuine AI extraction or faithfulness."""

from app.memory_contracts import MemoryExtractionRequest, MemoryExtractionResult, RevisionPayload


class MockMemoryProvider:
    def extract(self, request: MemoryExtractionRequest) -> MemoryExtractionResult:
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
        )
