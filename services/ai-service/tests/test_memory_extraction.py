"""Guarded, synthetic-only Memory wire/provider tests. No application or network."""

import os
import sys
from pathlib import Path
from uuid import uuid4

if __name__ == "__main__":
    import asyncio  # noqa: F401 -- initialize platform runtime before socket prohibition
    import builtins
    import importlib.abc
    import io
    import socket

    os.environ.clear()
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    sys.dont_write_bytecode = True

    def blocked(*args, **kwargs):
        raise AssertionError("Network disabled for synthetic tests")

    for name in ("connect", "connect_ex", "bind", "listen", "accept"):
        setattr(socket.socket, name, blocked)
    socket.create_connection = blocked

    class OfflineImports(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path, target=None):
            if fullname.split(".")[0] in {"dotenv", "psycopg", "psycopg2", "sqlalchemy"}:
                raise AssertionError("Secret and database imports are disabled")

    sys.meta_path.insert(0, OfflineImports())
    original_open, original_io_open = builtins.open, io.open

    def protected_open(original):
        def checked(file, *args, **kwargs):
            if isinstance(file, (str, bytes, os.PathLike)) and Path(
                os.fsdecode(file)
            ).name.startswith(".env"):
                raise AssertionError("Secret files are disabled")
            return original(file, *args, **kwargs)

        return checked

    builtins.open = protected_open(original_open)
    io.open = protected_open(original_io_open)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import pytest

    raise SystemExit(
        pytest.main(
            [
                "--noconftest",
                "-p",
                "no:cacheprovider",
                "-q",
                str(Path(__file__).resolve()),
                *sys.argv[1:],
            ]
        )
    )

import pytest
from pydantic import ValidationError

from app.memory_contracts import MemoryExtractionRequest, MemoryExtractionResult, RevisionPayload
from app.memory_extraction import MemoryExtractionRunner, extract_memories
from app.providers.memory_mock import MockMemoryProvider
from app.providers.memory_registry import get_memory_provider


def request_data(**updates):
    result = {
        "request_id": uuid4(),
        "contract_version": "memory-extraction.v1",
        "source_message_id": uuid4(),
        "source_text": "  合成：我记不清年份。\n",
    }
    result.update(updates)
    return result


def payload_data(**updates):
    result = {
        "title": "  合成片段  ",
        "content": "  我记不清年份。\n",
        "time_text": None,
        "place": None,
        "emotion": None,
        "uncertainties": ["年份不确定"],
    }
    result.update(updates)
    return result


def result_data(request, **updates):
    result = {
        "request_id": request.request_id,
        "contract_version": request.contract_version,
        "source_message_id": request.source_message_id,
        "candidates": [payload_data()],
    }
    result.update(updates)
    return result


@pytest.fixture(scope="module")
def backend_schema():
    import importlib.util

    path = Path(__file__).resolve().parents[3] / "apps/backend/app/schemas/memory_workflow.py"
    spec = importlib.util.spec_from_file_location("backend_memory_wire_schema", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mock_preserves_source_without_fact_invention():
    request = MemoryExtractionRequest(**request_data())
    result = extract_memories(request)
    assert result == extract_memories(request)
    assert result.validate_binding(request) is result
    assert result.candidates[0].content == request.source_text
    assert result.candidates[0].time_text is result.candidates[0].place is None


@pytest.mark.parametrize("count", [0, 1, 20])
def test_dynamic_offline_provider_cardinality(count):
    class DynamicProvider:
        calls = 0

        def extract(self, request):
            self.calls += 1
            return result_data(
                request, candidates=[payload_data(title=f"合成{index}") for index in range(count)]
            )

    provider = DynamicProvider()
    result = MemoryExtractionRunner(provider).extract(MemoryExtractionRequest(**request_data()))
    assert len(result.candidates) == count
    assert provider.calls == 1


@pytest.mark.parametrize("identifier", ["deepseek", "gpt", "MOCK", "", None, [], 1])
def test_registry_no_fallback(identifier):
    with pytest.raises(ValueError, match="unavailable"):
        get_memory_provider(identifier)


def test_registry_only_mock():
    assert isinstance(get_memory_provider(), MockMemoryProvider)


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", ""),
        ("title", "  "),
        ("title", "x" * 201),
        ("content", ""),
        ("content", "\n"),
        ("content", "x" * 20001),
        ("content", 1),
        ("time_text", "x" * 201),
        ("place", "x" * 201),
        ("emotion", "x" * 101),
        ("emotion", 1),
        ("confidence", 0.9),
        ("uncertainties", ["x" * 1001]),
        ("uncertainties", [""]),
        ("uncertainties", [1]),
        ("uncertainties", ["x"] * 21),
        ("uncertainties", "not-an-array"),
        ("uncertainties", None),
    ],
)
def test_payload_rejects_invalid(field, value):
    with pytest.raises(ValidationError):
        RevisionPayload(**payload_data(**{field: value}))


@pytest.mark.parametrize("field", ["time_text", "place", "emotion", "uncertainties"])
def test_nullable_and_list_fields_are_required(field):
    data = payload_data()
    del data[field]
    with pytest.raises(ValidationError):
        RevisionPayload(**data)


def test_payload_exact_limits_and_preservation():
    payload = RevisionPayload(**payload_data())
    assert payload.title == "  合成片段  "
    assert payload.content == "  我记不清年份。\n"
    assert payload.time_text is None
    full = RevisionPayload(
        **payload_data(
            title="x" * 200,
            content="x" * 20000,
            time_text="x" * 200,
            place="x" * 200,
            emotion="x" * 100,
            uncertainties=["x" * 1000] * 20,
        )
    )
    assert len(full.content) == 20000


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_text", ""),
        ("source_text", " "),
        ("source_text", 1),
        ("source_text", "x" * 10001),
        ("contract_version", "memory-extraction.v2"),
        ("token", "synthetic-secret-not-transmitted"),
        ("memory_context", []),
    ],
)
def test_request_rejects_private_extra_and_limits(field, value):
    with pytest.raises(ValidationError):
        MemoryExtractionRequest(**request_data(**{field: value}))


@pytest.mark.parametrize("field", ["request_id", "source_message_id"])
def test_echo_binding_mismatch(field):
    request = MemoryExtractionRequest(**request_data())
    result = MemoryExtractionResult(**result_data(request, **{field: uuid4()}))
    with pytest.raises(ValueError, match="binding"):
        result.validate_binding(request)


@pytest.mark.parametrize(
    "updates",
    [
        {"candidates": [payload_data()] * 21},
        {"candidates": "invalid"},
        {"confidence": 0.8},
        {"review_state": "approved"},
        {"contract_version": "memory-extraction.v2"},
    ],
)
def test_result_strict(updates):
    request = MemoryExtractionRequest(**request_data())
    with pytest.raises(ValidationError):
        MemoryExtractionResult(**result_data(request, **updates))


@pytest.mark.parametrize(
    "field", ["request_id", "contract_version", "source_message_id", "candidates"]
)
def test_result_echo_fields_are_required(field):
    request = MemoryExtractionRequest(**request_data())
    data = result_data(request)
    del data[field]
    with pytest.raises(ValidationError):
        MemoryExtractionResult(**data)


def test_nested_immutable_and_unsafe_copy_revalidation():
    raw = payload_data()
    payload = RevisionPayload(**raw)
    raw["uncertainties"].clear()
    assert payload.uncertainties == ("年份不确定",)
    with pytest.raises(ValidationError):
        payload.title = "changed"

    class InvalidProvider:
        def extract(self, request):
            return MemoryExtractionResult(**result_data(request)).model_copy(
                update={"candidates": [payload.model_copy(update={"content": " "})]}
            )

    with pytest.raises(ValidationError):
        MemoryExtractionRunner(InvalidProvider()).extract(MemoryExtractionRequest(**request_data()))


def test_only_stub_timeouterror_no_deadline_claim():
    class TimeoutProvider:
        def extract(self, request):
            raise TimeoutError("Synthetic timeout")

    with pytest.raises(TimeoutError):
        extract_memories(MemoryExtractionRequest(**request_data()), TimeoutProvider())


@pytest.mark.parametrize("count", [0, 1, 20])
def test_bidirectional_json_wire(backend_schema, count):
    request = MemoryExtractionRequest(**request_data(source_text="x" * 10000))
    backend_request = backend_schema.MemoryExtractionRequest.model_validate_json(
        request.model_dump_json()
    )
    assert MemoryExtractionRequest.model_validate_json(backend_request.model_dump_json()) == request
    result = MemoryExtractionResult(**result_data(request, candidates=[payload_data()] * count))
    backend_result = backend_schema.MemoryExtractionResult.model_validate_json(
        result.model_dump_json()
    )
    assert MemoryExtractionResult.model_validate_json(backend_result.model_dump_json()) == result
    assert backend_result.validate_binding(backend_request) is backend_result
    assert backend_result.model_dump(mode="json") == result.model_dump(mode="json")
