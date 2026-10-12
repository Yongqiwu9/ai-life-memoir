"""Guarded synthetic contract/provider tests; no live service or database execution."""

import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

if __name__ == "__main__":
    import asyncio  # noqa: F401 -- initialize Windows runtime before disabling sockets
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

from app.contracts import (
    CONTRACT_VERSION,
    MAX_QUESTIONS,
    AskedQuestion,
    QuestionRequest,
    QuestionResult,
)
from app.interview_agent import (
    QUESTION_CATALOG,
    InterviewAgentRunner,
    next_question,
    normalize_question,
)
from app.providers.mock import MockAIProvider
from app.providers.registry import get_provider


def request_data(**changes):
    data = {
        "request_id": uuid4(),
        "session_id": uuid4(),
        "agent_version": 3,
        "generation_epoch": 2,
        "context_message_ids": [],
        "context_text": None,
        "asked_questions": [],
    }
    data.update(changes)
    return data


def result_data(request=None, **changes):
    request = QuestionRequest(**request_data()) if request is None else request
    data = {
        name: getattr(request, name)
        for name in (
            "contract_version",
            "request_id",
            "session_id",
            "policy_version",
            "agent_version",
            "generation_epoch",
            "context_message_ids",
        )
    }
    data.update(
        outcome="question",
        question_key="synthetic-outside-catalog",
        question="合成测试：您愿意谈谈自己选择的回忆吗？",
        question_basis="neutral",
        basis_message_ids=[],
    )
    data.update(changes)
    return data


@pytest.fixture(scope="module")
def backend_schema():
    # Load a standalone Schema only, without importing either Backend application.
    import importlib.util

    path = Path(__file__).resolve().parents[3] / "apps/backend/app/schemas/interview_agent.py"
    spec = importlib.util.spec_from_file_location("backend_wire_schema", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "text,expected,basis",
    [
        (None, "opening", "neutral"),
        ("合成：上学", "school", "follow_up"),
        ("合成回忆", "opening", "neutral"),
    ],
)
def test_deterministic_branch(text, expected, basis):
    request = QuestionRequest(
        **request_data(context_message_ids=[uuid4()] if text else [], context_text=text)
    )
    result = next_question(request)
    assert result == next_question(request)
    assert result.question_key == expected
    assert result.question_basis == basis
    assert result.validate_binding(request) is result
    assert result.basis_message_ids == (request.context_message_ids if basis == "follow_up" else ())


def test_catalog_exhaustion_and_no_repeats():
    asked = []
    for _ in QUESTION_CATALOG:
        result = next_question(QuestionRequest(**request_data(asked_questions=asked)))
        assert result.question_key not in {item.question_key for item in asked}
        asked.append(
            AskedQuestion(
                message_id=uuid4(), question_key=result.question_key, text=result.question
            )
        )
    result = next_question(QuestionRequest(**request_data(asked_questions=asked)))
    assert result.outcome == "no_question"
    assert result.question is result.question_key is result.question_basis is None
    assert result.basis_message_ids == ()


def test_normalized_text_dedup_not_semantic():
    request = QuestionRequest(
        **request_data(
            asked_questions=[
                AskedQuestion(
                    message_id=uuid4(), question_key="another-key", text=" 您想从哪段回忆开始讲起? "
                )
            ]
        )
    )
    result = next_question(request)
    assert result.question_key == "story"
    assert normalize_question(result.question) != normalize_question(QUESTION_CATALOG[0][1])
    assert normalize_question("Ａ， Ｂ！") == "ab"
    assert normalize_question("您想聊什么？") != normalize_question("您愿意说些什么？")


class NewQuestionProvider:
    def __init__(self):
        self.calls = 0

    def generate_question(self, context):
        self.calls += 1
        return QuestionResult(**result_data(context))


def test_provider_can_replace_mock_with_new_synthetic_question():
    provider = NewQuestionProvider()
    runner = InterviewAgentRunner(provider)
    result = runner.next_question(QuestionRequest(**request_data()))
    assert provider.calls == 1
    assert result.question_key not in {key for key, _ in QUESTION_CATALOG}
    assert result.question not in {text for _, text in QUESTION_CATALOG}


@pytest.mark.parametrize("identifier", ["unknown", "gpt", "deepseek", "MOCK", "", None, []])
def test_unknown_provider_never_falls_back(identifier):
    with pytest.raises(ValueError, match="Provider is unavailable"):
        get_provider(identifier)


def test_only_mock_is_registered():
    assert isinstance(get_provider(), MockAIProvider)
    assert isinstance(get_provider("mock"), MockAIProvider)


@pytest.mark.parametrize(
    "field",
    ["request_id", "session_id", "agent_version", "generation_epoch", "context_message_ids"],
)
def test_result_binding_rejects_different_values(field):
    request = QuestionRequest(**request_data(context_message_ids=[uuid4()], context_text="合成"))
    data = result_data(request)
    data[field] = (
        [uuid4()]
        if field == "context_message_ids"
        else getattr(request, field) + 1
        if field in {"agent_version", "generation_epoch"}
        else uuid4()
    )
    with pytest.raises(ValueError, match="binding"):
        QuestionResult(**data).validate_binding(request)


@pytest.mark.parametrize(
    "field,value",
    [("contract_version", "interview-agent.v1"), ("policy_version", "live"), ("unexpected", True)],
)
def test_request_rejects_unknown(field, value):
    with pytest.raises(ValidationError):
        QuestionRequest(**request_data(**{field: value}))


@pytest.mark.parametrize(
    "field,value",
    [("contract_version", "interview-agent.v1"), ("policy_version", "live"), ("confidence", 0.99)],
)
def test_result_rejects_unknown(field, value):
    with pytest.raises(ValidationError):
        QuestionResult(**result_data(**{field: value}))


@pytest.mark.parametrize("field", ["agent_version", "generation_epoch"])
@pytest.mark.parametrize("value", [True, False, -1, 1.2, "1", None])
def test_strict_nonnegative_numbers(field, value):
    with pytest.raises(ValidationError):
        QuestionRequest(**request_data(**{field: value}))
    with pytest.raises(ValidationError):
        QuestionResult(**result_data(**{field: value}))


@pytest.mark.parametrize(
    "changes",
    [
        {"context_message_ids": [uuid4(), uuid4()], "context_text": "合成"},
        {"context_message_ids": [uuid4()], "context_text": None},
        {"context_message_ids": [], "context_text": "合成"},
        {"context_message_ids": [uuid4()], "context_text": ""},
        {"context_message_ids": [uuid4()], "context_text": "  "},
        {"context_message_ids": [uuid4()], "context_text": "x" * 10001},
        {"context_message_ids": "not-an-array"},
        {"asked_questions": "not-an-array"},
    ],
)
def test_context_cardinality_and_pairing(changes):
    with pytest.raises(ValidationError):
        QuestionRequest(**request_data(**changes))


def test_exact_maximum_context_and_asked_questions():
    asked = [
        AskedQuestion(message_id=uuid4(), question_key=f"q{index}", text="合成问题？")
        for index in range(MAX_QUESTIONS)
    ]
    request = QuestionRequest(
        **request_data(
            context_message_ids=[uuid4()], context_text="x" * 10000, asked_questions=asked
        )
    )
    assert len(request.asked_questions) == 24
    with pytest.raises(ValidationError):
        QuestionRequest(
            **request_data(
                asked_questions=[
                    *asked,
                    AskedQuestion(message_id=uuid4(), question_key="q25", text="合成？"),
                ]
            )
        )
    with pytest.raises(ValidationError):
        QuestionRequest(**request_data(asked_questions=[asked[0], asked[0]]))


@pytest.mark.parametrize(
    "field,value",
    [
        ("question_key", ""),
        ("question_key", " "),
        ("question_key", "x" * 101),
        ("text", ""),
        ("text", " "),
        ("text", "x" * 121),
        ("unexpected", True),
    ],
)
def test_asked_question_constraints(field, value):
    data = {"message_id": uuid4(), "question_key": "one", "text": "合成？"}
    data[field] = value
    with pytest.raises(ValidationError):
        AskedQuestion(**data)


def test_models_and_nested_collections_are_immutable():
    ids, asked = [uuid4()], [{"message_id": uuid4(), "question_key": "one", "text": "合成？"}]
    request = QuestionRequest(
        **request_data(context_message_ids=ids, context_text="合成", asked_questions=asked)
    )
    ids.clear()
    asked[0]["text"] = "modified"
    asked.clear()
    assert len(request.context_message_ids) == len(request.asked_questions) == 1
    assert request.asked_questions[0].text == "合成？"
    with pytest.raises(ValidationError):
        request.agent_version = 999
    with pytest.raises(ValidationError):
        request.asked_questions[0].text = "changed"
    assert isinstance(request.context_message_ids, tuple)
    assert isinstance(request.asked_questions, tuple)


@pytest.mark.parametrize("use_context", [False, True])
@pytest.mark.parametrize(
    "outcome,basis", [("question", "neutral"), ("question", "follow_up"), ("no_question", None)]
)
def test_result_combinations(use_context, outcome, basis):
    request = QuestionRequest(
        **request_data(
            context_message_ids=[uuid4()] if use_context else [],
            context_text="合成" if use_context else None,
        )
    )
    data = result_data(request, outcome=outcome, question_basis=basis)
    if outcome == "no_question":
        data.update(question_key=None, question=None)
    elif basis == "follow_up":
        data["basis_message_ids"] = request.context_message_ids
    if basis == "follow_up" and not use_context:
        with pytest.raises(ValidationError):
            QuestionResult(**data)
    else:
        result = QuestionResult(**data)
        assert result.validate_binding(request) is result
        assert result.context_message_ids == request.context_message_ids


@pytest.mark.parametrize(
    "changes",
    [
        {"question_key": None},
        {"question": None},
        {"question_basis": None},
        {"question_key": ""},
        {"question_key": " "},
        {"question": " "},
        {"question": "x" * 121},
        {"basis_message_ids": [uuid4()]},
        {"question_basis": "follow_up", "basis_message_ids": [uuid4()]},
        {"basis_message_ids": [uuid4(), uuid4()]},
        {"basis_message_ids": "invalid"},
        {"outcome": "no_question"},
    ],
)
def test_illegal_result_combinations(changes):
    with pytest.raises(ValidationError):
        QuestionResult(**result_data(**changes))


def test_runner_revalidates_unsafe_model_copy():
    class InvalidProvider:
        def generate_question(self, context):
            return QuestionResult(**result_data(context)).model_copy(update={"question": " "})

    with pytest.raises(ValidationError):
        next_question(QuestionRequest(**request_data()), InvalidProvider())


@pytest.mark.parametrize("same_text", [False, True])
def test_runner_rejects_repeated_question(same_text):
    provider = NewQuestionProvider()
    request = QuestionRequest(
        **request_data(
            asked_questions=[
                AskedQuestion(
                    message_id=uuid4(),
                    question_key="other" if same_text else "synthetic-outside-catalog",
                    text="合成测试：您愿意谈谈自己选择的回忆吗?" if same_text else "其他合成问题？",
                )
            ]
        )
    )
    with pytest.raises(ValueError, match="repeated"):
        next_question(request, provider)
    assert provider.calls == 1


@pytest.mark.parametrize("context_text", [None, "合成：读书"])
def test_bidirectional_json_wire_compatibility(backend_schema, context_text):
    request = QuestionRequest(
        **request_data(
            context_message_ids=[uuid4()] if context_text else [],
            context_text=context_text,
            asked_questions=[
                AskedQuestion(message_id=uuid4(), question_key="prior", text="其他合成问题？")
            ],
        )
    )
    backend_request = backend_schema.QuestionRequest.model_validate_json(request.model_dump_json())
    rebuilt_request = QuestionRequest.model_validate_json(backend_request.model_dump_json())
    assert request == rebuilt_request
    assert backend_request.model_dump(mode="json") == request.model_dump(mode="json")
    assert isinstance(backend_request.context_message_ids, tuple)
    assert isinstance(backend_request.asked_questions, tuple)
    assert isinstance(request.model_dump(mode="json")["context_message_ids"], list)
    assert isinstance(request.model_dump(mode="json")["asked_questions"], list)
    result = next_question(request)
    backend_result = backend_schema.QuestionResult.model_validate_json(result.model_dump_json())
    rebuilt_result = QuestionResult.model_validate_json(backend_result.model_dump_json())
    assert result == rebuilt_result
    assert backend_result.validate_binding(backend_request) is backend_result


def test_no_question_wire_compatibility(backend_schema):
    request = QuestionRequest(**request_data(context_message_ids=[uuid4()], context_text="合成"))
    result = QuestionResult(
        **result_data(
            request, outcome="no_question", question_key=None, question=None, question_basis=None
        )
    )
    backend = backend_schema.QuestionResult.model_validate_json(result.model_dump_json())
    assert QuestionResult.model_validate_json(backend.model_dump_json()) == result


def test_api_request_is_required_v2_and_has_no_answer(backend_schema):
    data = {
        "contract_version": CONTRACT_VERSION,
        "action": "request_question",
        "expected_version": 3,
    }
    assert backend_schema.AgentTurnCreate(**data).action == "request_question"
    for changes in (
        {"contract_version": "interview-agent.v1"},
        {"expected_version": True},
        {"action": "answer"},
        {"answer_message_id": uuid4()},
        {"user_id": uuid4()},
        {"provider": "mock"},
    ):
        with pytest.raises(ValidationError):
            backend_schema.AgentTurnCreate(**{**data, **changes})
    with pytest.raises(ValidationError):
        backend_schema.AgentTurnCreate(action="start", expected_version=0)


@pytest.mark.parametrize(
    "version,status",
    [
        ("interview-agent.v1", "awaiting_answer"),
        (CONTRACT_VERSION, "listening"),
        (CONTRACT_VERSION, "paused"),
    ],
)
def test_state_metadata_versioned_status(backend_schema, version, status):
    data = {
        "session_id": uuid4(),
        "contract_version": version,
        "status": status,
        "version": 0,
        "generation_epoch": 0,
        "session_status": "active",
    }
    state = backend_schema.AgentStateRead(**data)
    assert set(state.model_dump()) == {
        "session_id",
        "contract_version",
        "status",
        "version",
        "generation_epoch",
        "session_status",
        "pending_turn_id",
        "current_question_message_id",
    }
    opposite = CONTRACT_VERSION if version == "interview-agent.v1" else "interview-agent.v1"
    with pytest.raises(ValidationError):
        backend_schema.AgentStateRead(**{**data, "contract_version": opposite})


def turn_metadata(**changes):
    now = datetime.now(UTC)
    data = {
        "id": uuid4(),
        "session_id": uuid4(),
        "contract_version": CONTRACT_VERSION,
        "action": "request_question",
        "execution_status": "pending",
        "created_at": now,
        "finished_at": None,
    }
    data.update(changes)
    return data


@pytest.mark.parametrize("status", ["pending", "failed", "discarded"])
def test_turn_nullable_execution_metadata(backend_schema, status):
    extra = {} if status == "pending" else {"finished_at": datetime.now(UTC)}
    if status == "failed":
        extra["failure_code"] = "AI_UNAVAILABLE"
    if status == "discarded":
        extra["discard_reason"] = "STATE_CHANGED"
    turn = backend_schema.AgentTurnRead(**turn_metadata(execution_status=status, **extra))
    assert turn.result_kind is turn.resulting_status is turn.output_message_id is None
    assert "question_key" not in turn.model_dump()
    assert "input_answer_id" not in turn.model_dump()
    with pytest.raises(ValidationError):
        backend_schema.AgentTurnRead(**{**turn.model_dump(), "resulting_version": 7})


@pytest.mark.parametrize("version", ["interview-agent.v1", CONTRACT_VERSION])
def test_legacy_and_v2_completed_metadata(backend_schema, version):
    turn = backend_schema.AgentTurnRead(
        **turn_metadata(
            contract_version=version,
            execution_status="completed",
            action="start",
            result_kind="question" if version == "interview-agent.v1" else "control",
            result_state_contract_version=version,
            resulting_version=1,
            resulting_status="awaiting_answer" if version == "interview-agent.v1" else "listening",
            finished_at=None if version == "interview-agent.v1" else datetime.now(UTC),
        )
    )
    assert turn.resulting_version == 1


def test_explicit_v2_end_can_preserve_legacy_result_state(backend_schema):
    turn = backend_schema.AgentTurnRead(
        **turn_metadata(
            execution_status="completed",
            action="end",
            result_kind="control",
            result_state_contract_version="interview-agent.v1",
            resulting_version=2,
            resulting_status="ended",
            finished_at=datetime.now(UTC),
        )
    )
    assert turn.contract_version != turn.result_state_contract_version
    with pytest.raises(ValidationError):
        backend_schema.AgentTurnRead(**{**turn.model_dump(), "resulting_status": "idle"})


def test_deleted_question_output_is_nullable_metadata(backend_schema):
    turn = backend_schema.AgentTurnRead(
        **turn_metadata(
            execution_status="completed",
            result_kind="question",
            result_state_contract_version=CONTRACT_VERSION,
            resulting_version=4,
            resulting_status="listening",
            finished_at=datetime.now(UTC),
            output_message_id=None,
        )
    )
    assert turn.result_kind == "question" and turn.output_message_id is None
