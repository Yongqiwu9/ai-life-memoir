"""Run with python -I -B <this-file>, never bare pytest before isolation bootstrap."""

import os
import sys
from pathlib import Path


def install_offline_guards():
    """Before application/conftest imports: no dotenv, sockets or non-memory databases."""
    import socket
    import sqlite3

    import dotenv
    import psycopg
    import pydantic_settings
    import sqlalchemy
    from sqlalchemy.engine import make_url

    # Replace the child process environment, without reading inherited secret values.
    os.environ.clear()
    os.environ.update(
        JWT_SECRET_KEY="synthetic-offline-agent-test-key-at-least-32-bytes",
        DATABASE_URL="sqlite://",
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        PYTHONDONTWRITEBYTECODE="1",
    )
    sys.dont_write_bytecode = True

    def blocked(*args, **kwargs):
        raise AssertionError("Offline test isolation blocked forbidden operation")

    dotenv.load_dotenv = blocked
    dotenv.dotenv_values = blocked
    psycopg.connect = blocked
    psycopg.Connection.connect = blocked
    psycopg.AsyncConnection.connect = blocked
    # DotEnv's constructor loads files before __call__; disable both paths.
    pydantic_settings.DotEnvSettingsSource._read_env_files = lambda self: {}
    pydantic_settings.DotEnvSettingsSource.__call__ = lambda self: {}
    pydantic_settings.SecretsSettingsSource.__call__ = lambda self: {}
    for name in ("connect", "connect_ex", "bind", "listen", "accept"):
        setattr(socket.socket, name, blocked)
    socket.create_connection = blocked
    original_connect = sqlite3.dbapi2.connect

    def memory_connect(database, *args, **kwargs):
        if database != ":memory:":
            return blocked()
        return original_connect(database, *args, **kwargs)

    sqlite3.connect = memory_connect
    sqlite3.dbapi2.connect = memory_connect
    original_engine = sqlalchemy.create_engine

    def memory_engine(url, **kwargs):
        parsed = make_url(url)
        if (
            parsed.drivername not in ("sqlite", "sqlite+pysqlite")
            or parsed.database
            not in (
                None,
                "",
                ":memory:",
            )
            or parsed.query
        ):
            return blocked()
        kwargs.pop("pool_size", None)
        kwargs.pop("max_overflow", None)
        return original_engine(url, **kwargs)

    sqlalchemy.create_engine = memory_engine


if __name__ == "__main__":
    install_offline_guards()
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

import json
import uuid
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, event, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException, app_exception_handler
from app.database import models_import  # noqa: F401
from app.database.base import Base
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.interview import Interview
from app.models.interview_agent import InterviewAgentState, InterviewAgentTurn
from app.models.interview_message import InterviewMessage
from app.models.interview_session import InterviewSession
from app.models.user import User
from app.schemas.interview_agent import (
    CONTRACT_VERSION,
    AgentTurnCreate,
    QuestionResult,
)
from app.schemas.interview_message import InterviewMessageCreate
from app.services import interview_agent as service
from app.services import interview_message as message_service
from app.services.ai_interview_client import (
    DeterministicMockClient,
    UnavailableProcessingDecision,
    get_interview_client,
)


class SyntheticDecision:
    def require(self, **kwargs):
        pass


@pytest.fixture
def records():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        assert db.scalar(text("PRAGMA foreign_keys")) == 1
        users = [
            User(email=f"synthetic-{index}@example.invalid", password_hash="synthetic-placeholder")
            for index in range(2)
        ]
        db.add_all(users)
        db.flush()
        sessions = []
        family_id = None
        # same-owner different member, same-owner different family, other owner.
        for index, owner in enumerate((users[0], users[0], users[0], users[1])):
            if index == 1:
                family = db.get(Family, family_id)
            else:
                family = Family(owner_id=owner.id, name="Synthetic family")
                db.add(family)
                db.flush()
                if index == 0:
                    family_id = family.id
            member = FamilyMember(family_id=family.id, name="Synthetic subject")
            db.add(member)
            db.flush()
            interview = Interview(family_member_id=member.id, title="Synthetic interview")
            db.add(interview)
            db.flush()
            session = InterviewSession(interview_id=interview.id)
            db.add(session)
            db.flush()
            sessions.append(session)
        db.commit()
        yield db, users, sessions
    engine.dispose()


def turn(
    records, action="start", version=None, key=None, client=None, decision=None, with_status=False
):
    db, users, sessions = records
    if version is None:
        version = service.get_state(db, users[0].id, sessions[0].id).version
    data = AgentTurnCreate(
        contract_version=CONTRACT_VERSION, action=action, expected_version=version
    )
    result = service.advance_with_status(
        db,
        users[0].id,
        sessions[0].id,
        data,
        key or uuid.uuid4(),
        decision or SyntheticDecision(),
        client or DeterministicMockClient(),
    )
    return result if with_status else result[0]


def answer(records, content="合成答案：我喜欢读书。", session_index=0):
    db, users, sessions = records
    return message_service.create_message(
        db,
        user_id=users[1 if session_index == 3 else 0].id,
        session_id=sessions[session_index].id,
        data=InterviewMessageCreate(content=content),
    )


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def error_body(exc):
    coroutine = app_exception_handler(None, exc)
    try:
        coroutine.send(None)
    except StopIteration as completed:
        response = completed.value
    else:
        coroutine.close()
        raise AssertionError("Serializer unexpectedly requires asynchronous I/O")
    return response.status_code, json.loads(response.body)


def result_for(request, **changes):
    data = {
        "contract_version": request.contract_version,
        "request_id": request.request_id,
        "session_id": request.session_id,
        "policy_version": request.policy_version,
        "agent_version": request.agent_version,
        "generation_epoch": request.generation_epoch,
        "context_message_ids": request.context_message_ids,
        "outcome": "question",
        "question_key": "dynamic-" + request.request_id.hex,
        "question": "这是题库外的合成问题 " + request.request_id.hex[:8] + "？",
        "question_basis": "neutral",
        "basis_message_ids": (),
    }
    data.update(changes)
    return QuestionResult.model_validate(data)


class SyntheticClient:
    provider_id = "mock"

    def __init__(self, db, callback=None):
        self.db = db
        self.requests = []
        self.callback = callback

    def next_question(self, request):
        assert not self.db.in_transaction(), "Provider must run without a DB transaction"
        self.requests.append(request)
        if self.callback is not None:
            return self.callback(request)
        return result_for(request)


def assert_code(code, callback):
    with pytest.raises(AppException) as caught:
        callback()
    assert caught.value.code == code
    return caught.value


def test_start_and_save_text_do_not_call_provider(records):
    db, users, sessions = records
    provider = Mock(provider_id="mock")
    started = turn(records, client=provider, decision=UnavailableProcessingDecision())
    assert started.result_kind == "control" and started.resulting_status == "listening"
    assert started.output_message_id is None and started.resulting_version == 1
    original = answer(records)
    assert original.content == "合成答案：我喜欢读书。"
    assert count(db, InterviewMessage) == 1
    provider.next_question.assert_not_called()
    state = service.get_state(db, users[0].id, sessions[0].id, UnavailableProcessingDecision())
    assert state.current_question_message_id is None and state.generation_epoch == 0


def test_neutral_then_dynamic_follow_up_preserves_original(records):
    db, _, _ = records
    turn(records)
    provider = SyntheticClient(db)
    first = turn(records, "request_question", client=provider)
    assert (
        not provider.requests[0].context_message_ids and provider.requests[0].context_text is None
    )
    original = answer(records)
    follow = SyntheticClient(
        db,
        lambda request: result_for(
            request,
            question_basis="follow_up",
            basis_message_ids=request.context_message_ids,
        ),
    )
    second = turn(records, "request_question", client=follow)
    request = follow.requests[0]
    assert (
        request.context_message_ids == (original.id,) and request.context_text == original.content
    )
    assert [item.message_id for item in request.asked_questions] == [first.output_message_id]
    assert second.resulting_version == 3
    assert db.get(InterviewMessage, original.id).content == original.content
    assert db.get(InterviewAgentState, first.session_id).last_consumed_answer_id is None


def test_latest_text_only_and_same_source_reuse(records):
    db, _, sessions = records
    turn(records)
    answer(records, "合成旧原文")
    latest = answer(records, "合成最新原文")
    for index in (1, 2, 3):
        answer(records, "其他访谈合成原文", session_index=index)
    from app.crud.interview_message import create_message_flush

    for role, source in (
        ("assistant", "ai_generated"),
        ("system", "system"),
        ("user", "audio_transcript"),
    ):
        create_message_flush(
            db, session_id=sessions[0].id, role=role, source=source, content="不得进入上下文"
        )
    db.commit()
    provider = SyntheticClient(db)
    one = turn(records, "request_question", client=provider)
    two = turn(records, "request_question", client=provider)
    assert all(request.context_message_ids == (latest.id,) for request in provider.requests)
    assert all(request.context_text == "合成最新原文" for request in provider.requests)
    assert len(provider.requests[1].asked_questions) == 1
    assert provider.requests[1].asked_questions[0].message_id == one.output_message_id
    assert two.resulting_version == 3
    assert count(db, InterviewMessage) == 10


@pytest.mark.parametrize("bad", [" ", "x" * 10001])
def test_invalid_latest_does_not_fall_back(records, bad):
    db, _, _ = records
    turn(records)
    answer(records, "合成有效旧原文")
    latest = answer(records, "临时合成原文")
    db.execute(update(InterviewMessage).where(InterviewMessage.id == latest.id).values(content=bad))
    db.commit()
    provider = SyntheticClient(db)
    assert_code("SOURCE_UNAVAILABLE", lambda: turn(records, "request_question", client=provider))
    assert not provider.requests and count(db, InterviewAgentTurn) == 1


def test_owner_isolation_and_metadata_no_body(records, monkeypatch):
    db, users, sessions = records
    started = turn(records)
    from app.crud import interview_agent as agent_crud

    monkeypatch.setattr(
        agent_crud, "message_content", Mock(side_effect=AssertionError("no body read"))
    )
    state = service.get_state(db, users[0].id, sessions[0].id, UnavailableProcessingDecision())
    assert state.status == "listening"
    assert service.get_turn(db, users[0].id, sessions[0].id, started.id).id == started.id
    failures = []
    for session_id, actor in ((sessions[0].id, users[1].id), (uuid.uuid4(), users[0].id)):
        failures.append(
            error_body(
                assert_code(
                    "NOT_FOUND",
                    lambda actor=actor, session_id=session_id: service.get_state(
                        db, actor, session_id
                    ),
                )
            )
        )
    assert failures[0] == failures[1]
    assert_code("NOT_FOUND", lambda: service.get_turn(db, users[0].id, sessions[1].id, started.id))


def test_default_processing_and_adapter_fail_closed(records):
    db, _, _ = records
    turn(records)
    provider = SyntheticClient(db)
    assert_code(
        "POLICY_UNAVAILABLE",
        lambda: turn(
            records,
            "request_question",
            client=provider,
            decision=UnavailableProcessingDecision(),
        ),
    )
    assert not provider.requests

    assert_code(
        "AI_UNAVAILABLE", lambda: turn(records, "request_question", client=get_interview_client())
    )
    unknown = Mock(provider_id="unlisted")
    assert_code("AI_UNAVAILABLE", lambda: turn(records, "request_question", client=unknown))
    unknown.next_question.assert_not_called()


def test_decision_precedes_all_content_reads(records, monkeypatch):
    db, _, _ = records
    turn(records)
    original = answer(records)
    from app.crud import interview_agent as agent_crud

    real = agent_crud.message_content
    permitted = set()

    class Decision:
        def require(self, *, source_ids, **kwargs):
            permitted.update(source_ids)

    def guarded(db, session_id, message_id):
        assert message_id in permitted
        return real(db, session_id, message_id)

    monkeypatch.setattr(agent_crud, "message_content", guarded)
    provider = SyntheticClient(db)
    turn(records, "request_question", client=provider, decision=Decision())
    assert original.id in permitted


def test_same_key_pending_and_different_key_conflict_zero_call(records):
    db, users, sessions = records
    turn(records)
    key = uuid.uuid4()
    waiting_client = SyntheticClient(db)
    observed = []

    def during(request):
        pending, status = turn(
            records, "request_question", version=1, key=key, client=waiting_client, with_status=True
        )
        observed.append((pending, status))
        state = service.get_state(db, users[0].id, sessions[0].id)
        assert state.pending_turn_id == request.request_id and state.status == "listening"
        db.rollback()
        assert_code(
            "AGENT_GENERATION_PENDING",
            lambda: turn(
                records,
                "request_question",
                version=1,
                client=waiting_client,
            ),
        )
        return result_for(request)

    provider = SyntheticClient(db, during)
    finished = turn(records, "request_question", version=1, key=key, client=provider)
    assert observed[0][1] == 202 and observed[0][0].execution_status == "pending"
    assert not waiting_client.requests and len(provider.requests) == 1
    assert finished.execution_status == "completed"


def test_completed_replay_precedes_version_and_source_selection(records, monkeypatch):
    db, _, _ = records
    turn(records)
    answer(records)
    key = uuid.uuid4()
    provider = SyntheticClient(db)
    original = turn(records, "request_question", version=1, key=key, client=provider)
    answer(records, "合成新来源不应用于重放")
    from app.crud import interview_agent as agent_crud

    monkeypatch.setattr(
        agent_crud, "latest_text_reference", Mock(side_effect=AssertionError("no reselection"))
    )
    replay, status = turn(
        records, "request_question", version=1, key=key, client=provider, with_status=True
    )
    assert status == 200 and replay == original and len(provider.requests) == 1
    assert_code(
        "IDEMPOTENCY_CONFLICT",
        lambda: turn(records, "request_question", version=2, key=key, client=provider),
    )


@pytest.mark.parametrize("operation", ["pause", "end", "pause_resume"])
def test_late_result_cannot_publish_after_control(records, operation):
    db, users, sessions = records
    turn(records)
    source = answer(records)

    def during(request):
        turn(records, "end" if operation == "end" else "pause")
        if operation == "pause_resume":
            answer(records, "暂停时允许追加的合成文字")
            turn(records, "resume")
        return result_for(request)

    provider = SyntheticClient(db, during)
    assert_code(
        "AGENT_RESULT_DISCARDED", lambda: turn(records, "request_question", client=provider)
    )
    request = provider.requests[0]
    old = db.get(InterviewAgentTurn, request.request_id)
    assert old.execution_status == "discarded"
    assert (
        db.scalar(
            select(func.count())
            .select_from(InterviewMessage)
            .where(InterviewMessage.role == "assistant")
        )
        == 0
    )
    state = service.get_state(db, users[0].id, sessions[0].id)
    assert state.generation_epoch == (2 if operation == "pause_resume" else 1)
    assert (
        state.status == {"pause": "paused", "end": "ended", "pause_resume": "listening"}[operation]
    )
    if operation == "end":
        assert db.get(InterviewSession, sessions[0].id).ended_at is not None
        assert db.get(InterviewMessage, source.id).content == source.content
        assert_code("SESSION_NOT_ACTIVE", lambda: answer(records))
    else:
        answer(records, "合成自由回忆")


def test_pause_keeps_question_and_never_reactivates_old_pending(records):
    db, _, _ = records
    turn(records)
    first = turn(records, "request_question", client=SyntheticClient(db))
    turn(records, "pause")
    state = db.get(InterviewAgentState, first.session_id)
    assert state.current_question_message_id == first.output_message_id
    answer(records)
    assert_code("AGENT_STATE_CONFLICT", lambda: turn(records, "request_question"))
    turn(records, "resume")
    turn(records, "request_question", client=SyntheticClient(db))
    assert state.generation_epoch == 2


def test_question_winning_before_end_and_control_replay_without_policy(records):
    db, _, sessions = records
    start_key = uuid.uuid4()
    turn(records, key=start_key)
    question = turn(records, "request_question", client=SyntheticClient(db))
    end_key = uuid.uuid4()
    end = turn(records, "end", key=end_key, decision=UnavailableProcessingDecision())
    assert end.resulting_version == 3 and sessions[0].status == "completed"
    assert db.get(InterviewMessage, question.output_message_id) is not None
    assert db.get(InterviewAgentState, sessions[0].id).current_question_message_id is None
    replay, status = turn(
        records,
        "end",
        version=2,
        key=end_key,
        decision=UnavailableProcessingDecision(),
        with_status=True,
    )
    assert status == 200 and replay.id == end.id


@pytest.mark.parametrize("action", ["start", "resume", "pause"])
def test_invalid_new_control_key_never_creates_turn(records, action):
    db, _, _ = records
    if action == "start":
        turn(records)
    before = count(db, InterviewAgentTurn)
    assert_code("AGENT_STATE_CONFLICT", lambda: turn(records, action))
    assert count(db, InterviewAgentTurn) == before


def test_new_text_during_generation_does_not_reselect_context(records):
    db, _, _ = records
    turn(records)
    first = answer(records, "合成原始上下文")

    def during(request):
        answer(records, "调用过程中新增的合成文字")
        return result_for(request)

    provider = SyntheticClient(db, during)
    generated = turn(records, "request_question", client=provider)
    assert provider.requests[0].context_message_ids == (first.id,)
    assert db.get(InterviewAgentTurn, generated.id).context_scope_id == first.id
    assert db.get(InterviewMessage, generated.output_message_id).sequence == 3


@pytest.mark.parametrize("change", ["modify", "delete", "revoke", "policy"])
def test_changed_source_or_policy_discard(records, change):
    db, _, _ = records
    turn(records)
    source = answer(records)
    revoked = False

    class Decision:
        def require(self, **kwargs):
            if revoked:
                raise AppException(
                    "synthetic-sensitive-marker", code="PROCESSING_DENIED", status_code=403
                )

    def during(request):
        nonlocal revoked
        if change == "modify":
            db.execute(
                update(InterviewMessage)
                .where(InterviewMessage.id == source.id)
                .values(content="被改动的合成原文")
            )
            db.commit()
        elif change == "delete":
            db.delete(source)
            db.commit()
        elif change == "policy":
            state = db.get(InterviewAgentState, source.session_id)
            state.policy_version = "disabled-policy"
            db.commit()
        else:
            revoked = True
        return result_for(request)

    provider = SyntheticClient(db, during)
    assert_code(
        "AGENT_RESULT_DISCARDED",
        lambda: turn(records, "request_question", client=provider, decision=Decision()),
    )
    assert (
        db.get(InterviewAgentTurn, provider.requests[0].request_id).execution_status == "discarded"
    )
    assert db.get(InterviewAgentState, source.session_id).version == 1
    assert (
        db.scalar(
            select(func.count())
            .select_from(InterviewMessage)
            .where(InterviewMessage.role == "assistant")
        )
        == 0
    )


def test_changed_asked_question_discards_and_dependency_body_not_reloaded(records, monkeypatch):
    db, _, _ = records
    turn(records)
    old = answer(records, "历史合成原文")
    first = turn(records, "request_question", client=SyntheticClient(db))
    latest = answer(records, "最新合成原文")
    from app.crud import interview_agent as agent_crud

    real = agent_crud.message_content
    reads = []

    def observed(db, session_id, message_id):
        reads.append(message_id)
        assert message_id != old.id
        return real(db, session_id, message_id)

    monkeypatch.setattr(agent_crud, "message_content", observed)

    def during(request):
        db.execute(
            update(InterviewMessage)
            .where(InterviewMessage.id == first.output_message_id)
            .values(content="变动的合成问句")
        )
        db.commit()
        return result_for(request)

    provider = SyntheticClient(db, during)
    assert_code(
        "AGENT_RESULT_DISCARDED", lambda: turn(records, "request_question", client=provider)
    )
    assert latest.id in reads and first.output_message_id in reads and old.id not in reads


@pytest.mark.parametrize(
    "damage", ["missing_context", "cross_session", "cycle", "order", "bad_json"]
)
def test_dependency_closure_fail_closed_on_replay(records, damage):
    db, _, sessions = records
    turn(records)
    source = answer(records)
    key = uuid.uuid4()
    first = turn(records, "request_question", version=1, key=key, client=SyntheticClient(db))
    stored = db.get(InterviewAgentTurn, first.id)
    if damage == "missing_context":
        db.delete(source)
    elif damage == "cross_session":
        outside = answer(records, "合成跨Session来源", session_index=1)
        stored.context_scope_id = outside.id
        stored.context_message_id = outside.id
    elif damage == "cycle":
        stored.asked_question_message_ids = [str(first.output_message_id)]
    elif damage == "order":
        source.sequence = 99
    else:
        stored.asked_question_message_ids = ["not-a-uuid"]
    db.commit()
    provider = SyntheticClient(db)
    assert_code(
        "IDEMPOTENCY_RESULT_UNAVAILABLE",
        lambda: turn(records, "request_question", version=1, key=key, client=provider),
    )
    assert not provider.requests and stored.output_scope_id == first.output_message_id
    assert service.get_turn(db, records[1][0].id, sessions[0].id, first.id).id == first.id


def test_m01_deleted_output_stable_key_cannot_republish(records):
    db, _, _ = records
    turn(records)
    key = uuid.uuid4()
    provider = SyntheticClient(db)
    first = turn(records, "request_question", version=1, key=key, client=provider)
    stored = db.get(InterviewAgentTurn, first.id)
    original_key = stored.question_key
    db.delete(db.get(InterviewMessage, first.output_message_id))
    db.commit()
    db.expire_all()
    assert_code(
        "IDEMPOTENCY_RESULT_UNAVAILABLE",
        lambda: turn(records, "request_question", version=1, key=key, client=provider),
    )
    stored = db.get(InterviewAgentTurn, first.id)
    assert stored.output_message_id is None and stored.output_scope_id == first.output_message_id
    duplicate = SyntheticClient(db, lambda request: result_for(request, question_key=original_key))
    assert_code("AI_INVALID_RESPONSE", lambda: turn(records, "request_question", client=duplicate))
    assert len(provider.requests) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("request_id", uuid.uuid4()),
        ("session_id", uuid.uuid4()),
        ("agent_version", 999),
        ("generation_epoch", 999),
        ("context_message_ids", (uuid.uuid4(),)),
    ],
)
def test_misbound_provider_result_fails_without_publish(records, field, value):
    db, _, _ = records
    turn(records)
    provider = SyntheticClient(db, lambda request: result_for(request, **{field: value}))
    assert_code("AI_INVALID_RESPONSE", lambda: turn(records, "request_question", client=provider))
    stored = db.get(InterviewAgentTurn, provider.requests[0].request_id)
    assert stored.execution_status == "failed" and stored.failure_code == "AI_INVALID_RESPONSE"
    assert count(db, InterviewMessage) == 0


@pytest.mark.parametrize(
    "failure,code",
    [
        (TimeoutError("synthetic-private"), "AI_PROVIDER_TIMEOUT"),
        (RuntimeError("synthetic-private"), "AI_UNAVAILABLE"),
        (ValueError("synthetic-private"), "AI_INVALID_RESPONSE"),
    ],
)
def test_provider_error_and_terminal_replay_no_calls_or_leak(records, failure, code, caplog):
    db, _, _ = records
    turn(records)
    key = uuid.uuid4()

    def during(request):
        raise failure

    provider = SyntheticClient(db, during)
    exc = assert_code(
        code, lambda: turn(records, "request_question", version=1, key=key, client=provider)
    )
    assert "synthetic-private" not in json.dumps(error_body(exc)) + caplog.text
    assert_code(
        code, lambda: turn(records, "request_question", version=1, key=key, client=provider)
    )
    assert len(provider.requests) == 1 and count(db, InterviewMessage) == 0


def test_result_duplicate_normalized_text_and_no_persisted_body_copy(records):
    db, _, _ = records
    turn(records)
    first = turn(
        records,
        "request_question",
        client=SyntheticClient(db, lambda req: result_for(req, question="Ｓｙｎｔｈｅｔｉｃ　？")),
    )
    duplicate = SyntheticClient(db, lambda req: result_for(req, question=" synthetic!! "))
    assert_code("AI_INVALID_RESPONSE", lambda: turn(records, "request_question", client=duplicate))
    stored = db.get(InterviewAgentTurn, first.id)
    assert stored.question_text_normalized is None
    assert len(stored.request_fingerprint) == 32


def test_no_question_keeps_state_and_current_question(records):
    db, _, sessions = records
    turn(records)
    first = turn(records, "request_question", client=SyntheticClient(db))
    source = answer(records)
    provider = SyntheticClient(
        db,
        lambda req: result_for(
            req,
            outcome="no_question",
            question_key=None,
            question=None,
            question_basis=None,
            basis_message_ids=(),
        ),
    )
    result = turn(records, "request_question", client=provider)
    state = db.get(InterviewAgentState, sessions[0].id)
    assert result.result_kind == "no_question" and result.resulting_version == 2
    assert state.status == "listening" and state.generation_epoch == 0
    assert state.current_question_message_id == first.output_message_id
    assert sessions[0].status == "active" and db.get(InterviewMessage, source.id) is not None


def test_question_cap_counts_deleted_outputs_not_controls_or_noquestion(records):
    db, _, _ = records
    turn(records)
    provider = SyntheticClient(db)
    for _ in range(24):
        generated = turn(records, "request_question", client=provider)
        db.delete(db.get(InterviewMessage, generated.output_message_id))
        db.commit()
        db.expire_all()
    assert_code("AGENT_QUESTION_LIMIT", lambda: turn(records, "request_question", client=provider))
    assert len(provider.requests) == 24
    turn(records, "pause", decision=UnavailableProcessingDecision())
    turn(records, "resume", decision=UnavailableProcessingDecision())
    end = turn(records, "end", decision=UnavailableProcessingDecision())
    assert end.result_kind == "control" and end.resulting_status == "ended"


def test_publish_rollback_and_failure_cleanup(records, monkeypatch):
    db, _, sessions = records
    turn(records)
    real = service.message_crud.create_message_flush

    def broken(*args, **kwargs):
        real(*args, **kwargs)
        raise RuntimeError("synthetic-sensitive-storage")

    monkeypatch.setattr(service.message_crud, "create_message_flush", broken)
    provider = SyntheticClient(db)
    assert_code(
        "AGENT_STORAGE_UNAVAILABLE", lambda: turn(records, "request_question", client=provider)
    )
    assert count(db, InterviewMessage) == 0
    assert db.get(InterviewAgentState, sessions[0].id).version == 1
    assert db.get(InterviewAgentTurn, provider.requests[0].request_id).execution_status == "failed"


def test_failure_cleanup_failure_leaves_pending_for_explicit_stop(records, monkeypatch):
    db, _, _ = records
    turn(records)
    real_commit = db.commit
    calls = 0

    def commit():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("synthetic-cleanup-failure")
        real_commit()

    monkeypatch.setattr(db, "commit", commit)
    provider = SyntheticClient(db, lambda request: (_ for _ in ()).throw(TimeoutError()))
    assert_code(
        "AGENT_STORAGE_UNAVAILABLE", lambda: turn(records, "request_question", client=provider)
    )
    stored = db.get(InterviewAgentTurn, provider.requests[0].request_id)
    assert stored.execution_status == "pending"
    monkeypatch.setattr(db, "commit", real_commit)
    turn(records, "pause")
    assert stored.execution_status == "discarded"


@pytest.mark.parametrize(
    "phase,committed,status,code",
    [
        ("reserve", True, 202, None),
        ("reserve", False, None, "AGENT_COMMIT_UNCERTAIN"),
        ("publish", True, 200, None),
        ("publish", False, 202, None),
        ("control", True, 200, None),
        ("control", False, None, "AGENT_COMMIT_UNCERTAIN"),
    ],
)
def test_commit_uncertainty_never_repeats_provider_or_control(
    records, monkeypatch, phase, committed, status, code
):
    db, _, sessions = records
    turn(records)
    real_commit = db.commit
    calls = 0
    provider = SyntheticClient(db)

    def uncertain():
        nonlocal calls
        calls += 1
        if calls == (2 if phase == "publish" else 1):
            if committed:
                real_commit()
            raise RuntimeError("synthetic-commit-outcome")
        real_commit()

    monkeypatch.setattr(db, "commit", uncertain)
    action = "pause" if phase == "control" else "request_question"
    if code:
        assert_code(code, lambda: turn(records, action, client=provider, with_status=True))
    else:
        result, actual = turn(records, action, client=provider, with_status=True)
        assert actual == status
        assert result.execution_status == ("pending" if status == 202 else "completed")
    assert len(provider.requests) == (1 if phase == "publish" else 0)
    db.expire_all()
    state = db.get(InterviewAgentState, sessions[0].id)
    assert state.version == (2 if committed and phase in {"publish", "control"} else 1)


def test_source_deleted_during_generation_and_session_deleted_no_resurrection(records):
    db, users, sessions = records
    turn(records)
    session_id = sessions[0].id

    def during(request):
        db.delete(db.get(InterviewSession, session_id))
        db.commit()
        return result_for(request)

    provider = SyntheticClient(db, during)
    assert_code("NOT_FOUND", lambda: turn(records, "request_question", client=provider))
    assert db.get(InterviewSession, session_id) is None
    assert count(db, InterviewAgentState) == 0 and count(db, InterviewAgentTurn) == 0
    assert_code("NOT_FOUND", lambda: service.get_state(db, users[0].id, session_id))


def test_legacy_state_read_only_except_explicit_end(records):
    db, users, sessions = records
    state = InterviewAgentState(
        session_id=sessions[0].id,
        contract_version="interview-agent.v1",
        status="awaiting_answer",
        version=7,
        generation_epoch=0,
        policy_version="legacy-policy",
    )
    db.add(state)
    db.commit()
    observed = service.get_state(db, users[0].id, sessions[0].id)
    assert (
        observed.status == "awaiting_answer" and observed.contract_version == "interview-agent.v1"
    )
    assert_code("LEGACY_AGENT_SESSION", lambda: turn(records, "request_question", version=7))
    ended = turn(records, "end", version=7, decision=UnavailableProcessingDecision())
    assert (
        ended.contract_version == CONTRACT_VERSION
        and ended.result_state_contract_version == "interview-agent.v1"
    )
    assert ended.resulting_status == "ended" and ended.resulting_version == 8
    assert sessions[0].status == "completed" and state.contract_version == "interview-agent.v1"


def test_history_without_state_is_not_repaired(records):
    db, _, sessions = records
    turn(records)
    db.delete(db.get(InterviewAgentState, sessions[0].id))
    db.commit()
    assert_code("AGENT_STATE_UNAVAILABLE", lambda: turn(records, "start", version=0))
    assert count(db, InterviewAgentState) == 0


def test_db_constraints_reject_incomplete_terminal_and_duplicate_pending(records):
    db, users, sessions = records
    turn(records)

    def during(request):
        original = db.get(InterviewAgentTurn, request.request_id)
        duplicate = InterviewAgentTurn(
            session_id=sessions[0].id,
            actor_user_id=users[0].id,
            idempotency_key=uuid.uuid4(),
            contract_version=CONTRACT_VERSION,
            action="request_question",
            request_fingerprint=b"x" * 32,
            reserved_version=1,
            reserved_epoch=0,
            execution_status="pending",
            context_present=False,
            asked_question_message_ids=[],
            provider_id="mock",
        )
        db.add(duplicate)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
        original = db.get(InterviewAgentTurn, request.request_id)
        original.execution_status = "completed"
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
        return result_for(request)

    provider = SyntheticClient(db, during)
    generated = turn(records, "request_question", client=provider)
    assert generated.execution_status == "completed"


def test_migration_source_static_contract_only():
    import ast

    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/a196e4c72b08_interview_agent_provider_extension.py"
    )
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assignments = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"revision", "down_revision"}
    }
    assert assignments == {"revision": "a196e4c72b08", "down_revision": "f3a96b10d207"}
    assert "question_text_normalized" in source and "output_scope_id" in source
    assert "interview-agent.v2" in source and "downgrade" in source
    assert set(InterviewAgentState.__table__.columns.keys()) == {
        # Legacy v1/v2 fields remain complete.
        "session_id",
        "contract_version",
        "status",
        "version",
        "generation_epoch",
        "current_question_message_id",
        "last_consumed_answer_id",
        "policy_version",
        "created_at",
        "updated_at",
    } | {
        # Exact approved C2 additions; unexpected columns must fail.
        "integration_profile",
        "persistence_version",
        "stop_fence",
        "last_applied_event_seq",
        "next_command_order",
        "checkpoint_status",
        "effective_mode",
        "current_context_revision",
        "clock_origin_at",
        "active_command_id",
    }
    assert set(InterviewAgentTurn.__table__.columns.keys()) == {
        # Legacy v1/v2 fields remain complete.
        "id",
        "session_id",
        "actor_user_id",
        "idempotency_key",
        "contract_version",
        "action",
        "request_fingerprint",
        "reserved_version",
        "reserved_epoch",
        "execution_status",
        "context_present",
        "context_message_id",
        "context_scope_id",
        "asked_question_message_ids",
        "provider_id",
        "input_answer_id",
        "output_message_id",
        "output_scope_id",
        "question_key",
        "question_text_normalized",
        "result_kind",
        "result_state_contract_version",
        "resulting_version",
        "resulting_status",
        "failure_code",
        "discard_reason",
        "created_at",
        "updated_at",
        "finished_at",
    } | {
        # Exact approved C2 additions; unexpected columns must fail.
        "integration_profile",
        "command_order",
        "event_id",
        "event_kind",
        "command_payload",
        "reserved_event_seq",
        "applied_event_seq",
        "reserved_persistence_version",
        "reserved_stop_fence",
        "fingerprint_key_id",
        "result_metadata",
        "parent_turn_id",
        "internal_reason",
        "event_envelope",
        "transition_attempts",
    }


def test_end_does_not_complete_interview_and_legacy_end_replays(records):
    db, _, sessions = records
    interview = db.get(Interview, sessions[0].interview_id)
    original_status = interview.status
    legacy = InterviewAgentState(
        session_id=sessions[0].id,
        contract_version="interview-agent.v1",
        status="awaiting_answer",
        version=2,
        generation_epoch=0,
        policy_version="unknown-legacy",
    )
    db.add(legacy)
    db.commit()
    key = uuid.uuid4()
    ended = turn(records, "end", version=2, key=key, decision=UnavailableProcessingDecision())
    replay, status = turn(
        records,
        "end",
        version=2,
        key=key,
        decision=UnavailableProcessingDecision(),
        with_status=True,
    )
    assert status == 200 and replay == ended
    assert interview.status == original_status and sessions[0].status == "completed"


def test_failure_cleanup_never_overwrites_discard(records):
    db, _, _ = records
    turn(records)

    def during(request):
        turn(records, "pause")
        raise TimeoutError("synthetic-late-error")

    provider = SyntheticClient(db, during)
    assert_code("AI_PROVIDER_TIMEOUT", lambda: turn(records, "request_question", client=provider))
    stored = db.get(InterviewAgentTurn, provider.requests[0].request_id)
    assert stored.execution_status == "discarded" and stored.failure_code is None
    assert stored.discard_reason == "AGENT_PAUSED"


def test_revoked_history_omitted_but_published_key_not_reusable(records, monkeypatch):
    db, _, _ = records
    turn(records)
    first = turn(
        records,
        "request_question",
        client=SyntheticClient(
            db, lambda request: result_for(request, question_key="published-key")
        ),
    )
    from app.crud import interview_agent as agent_crud

    real = agent_crud.message_content

    class Decision:
        def require(self, *, source_ids, **kwargs):
            if first.output_message_id in source_ids:
                raise AppException("restricted", code="PROCESSING_DENIED", status_code=403)

    def guarded(db, session_id, message_id):
        assert message_id != first.output_message_id
        return real(db, session_id, message_id)

    monkeypatch.setattr(agent_crud, "message_content", guarded)
    provider = SyntheticClient(
        db, lambda request: result_for(request, question_key="published-key")
    )
    assert_code(
        "AI_INVALID_RESPONSE",
        lambda: turn(records, "request_question", client=provider, decision=Decision()),
    )
    assert provider.requests[0].asked_questions == ()


def test_no_question_replay_rechecks_current_permissions(records):
    db, _, _ = records
    turn(records)
    source = answer(records)
    key = uuid.uuid4()
    provider = SyntheticClient(
        db,
        lambda request: result_for(
            request,
            outcome="no_question",
            question_key=None,
            question=None,
            question_basis=None,
        ),
    )
    original = turn(records, "request_question", version=1, key=key, client=provider)
    assert original.result_kind == "no_question"

    class Decision:
        def require(self, *, source_ids, **kwargs):
            assert source.id in source_ids
            raise AppException("synthetic-sensitive", code="PROCESSING_DENIED", status_code=403)

    assert_code(
        "PROCESSING_DENIED",
        lambda: turn(
            records,
            "request_question",
            version=1,
            key=key,
            client=provider,
            decision=Decision(),
        ),
    )
    assert len(provider.requests) == 1


def test_control_commit_failure_rolls_back_both_state_and_session(records, monkeypatch):
    db, _, sessions = records
    turn(records)
    session_id = sessions[0].id

    def failure():
        raise RuntimeError("synthetic-storage-outcome")

    monkeypatch.setattr(db, "commit", failure)
    assert_code("AGENT_COMMIT_UNCERTAIN", lambda: turn(records, "end"))
    db.expire_all()
    state = db.get(InterviewAgentState, session_id)
    session = db.get(InterviewSession, session_id)
    assert state.status == "listening" and state.version == 1 and state.generation_epoch == 0
    assert session.status == "active" and session.ended_at is None


def test_same_meaning_different_questions_are_not_semantically_deduplicated(records):
    db, _, _ = records
    turn(records)
    first = SyntheticClient(db, lambda req: result_for(req, question="您愿意多说一些吗？"))
    second = SyntheticClient(db, lambda req: result_for(req, question="还想补充哪些内容呢？"))
    turn(records, "request_question", client=first)
    generated = turn(records, "request_question", client=second)
    assert generated.execution_status == "completed"


def test_provider_immutable_dto_cannot_be_corrupted_by_construct(records):
    db, _, _ = records
    turn(records)

    def invalid(request):
        valid = result_for(request)
        return valid.model_copy(update={"agent_version": True, "question": ""})

    provider = SyntheticClient(db, invalid)
    assert_code("AI_INVALID_RESPONSE", lambda: turn(records, "request_question", client=provider))
    assert count(db, InterviewMessage) == 0


def test_fingerprint_uses_intent_only_and_no_source_body_digest(records):
    import hashlib

    db, users, sessions = records
    turn(records)
    source = answer(records, "synthetic-body-marker")
    key = uuid.uuid4()
    generated = turn(records, "request_question", version=1, key=key, client=SyntheticClient(db))
    payload = {
        "actor_user_id": str(users[0].id),
        "session_id": str(sessions[0].id),
        "contract_version": CONTRACT_VERSION,
        "action": "request_question",
        "expected_version": 1,
    }
    expected = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).digest()
    stored = db.get(InterviewAgentTurn, generated.id)
    assert stored.request_fingerprint == expected
    assert stored.context_scope_id == source.id and stored.question_text_normalized is None


def test_legacy_turn_get_is_metadata_only_and_does_not_certify_unknown_sources(
    records, monkeypatch
):
    db, users, sessions = records
    state = InterviewAgentState(
        session_id=sessions[0].id,
        contract_version="interview-agent.v1",
        status="ended",
        version=3,
        generation_epoch=0,
        policy_version="unknown-legacy",
    )
    old = InterviewAgentTurn(
        session_id=sessions[0].id,
        actor_user_id=users[0].id,
        idempotency_key=uuid.uuid4(),
        contract_version="interview-agent.v1",
        action="start",
        request_fingerprint=b"x" * 32,
        execution_status="completed",
        result_kind="question",
        result_state_contract_version="interview-agent.v1",
        resulting_version=1,
        resulting_status="awaiting_answer",
        question_key="legacy-key",
        question_text_normalized="synthetic-legacy-body",
    )
    db.add_all((state, old))
    db.commit()
    from app.crud import interview_agent as agent_crud

    monkeypatch.setattr(
        agent_crud, "message_content", Mock(side_effect=AssertionError("metadata only"))
    )
    metadata = service.get_turn(db, users[0].id, sessions[0].id, old.id)
    assert metadata.output_message_id is None and metadata.finished_at is None
    assert metadata.contract_version == "interview-agent.v1"
    assert "synthetic-legacy-body" not in metadata.model_dump_json()
    assert old.context_present is None and old.context_scope_id is None


def test_migration_alembic_call_signatures_static_only():
    import ast

    source = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/a196e4c72b08_interview_agent_provider_extension.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    signatures = {
        "create_foreign_key": 5,
        "create_index": 3,
        "create_check_constraint": 3,
        "drop_index": 1,
        "drop_constraint": 2,
        "add_column": 2,
        "drop_column": 2,
        "alter_column": 2,
    }
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "op"
        ):
            name = node.func.attr
            if name in signatures:
                assert len(node.args) >= signatures[name], (name, node.lineno)
                assert not isinstance(node.args[0], ast.Tuple), (name, node.lineno)
        if (
            isinstance(node, ast.For)
            and isinstance(node.target, ast.Name)
            and node.target.id == "name"
            and isinstance(node.iter, ast.Tuple)
        ):
            assert all(
                isinstance(item, ast.Constant) and isinstance(item.value, str)
                for item in node.iter.elts
            )


@pytest.mark.parametrize("action", ["start", "pause", "resume", "end"])
@pytest.mark.parametrize("committed", [False, True])
def test_all_control_uncertain_commits_are_reconciled_without_duplicate_effects(
    records, monkeypatch, action, committed
):
    db, users, sessions = records
    if action != "start":
        turn(records)
    if action == "resume":
        turn(records, "pause")
    state_before = service.get_state(db, users[0].id, sessions[0].id)
    before_count = count(db, InterviewAgentTurn)
    db.rollback()
    version = state_before.version
    key = uuid.uuid4()
    real_commit = db.commit
    provider = SyntheticClient(db)

    def uncertain():
        if committed:
            real_commit()
        raise RuntimeError("synthetic-control-response-loss")

    monkeypatch.setattr(db, "commit", uncertain)
    if not committed:
        assert_code(
            "AGENT_COMMIT_UNCERTAIN",
            lambda: turn(records, action, version=version, key=key, client=provider),
        )
        db.expire_all()
        after = service.get_state(db, users[0].id, sessions[0].id)
        assert after.version == version and after.generation_epoch == state_before.generation_epoch
        assert sessions[0].status == "active" and sessions[0].ended_at is None
        assert count(db, InterviewAgentTurn) == before_count
    else:
        completed, status = turn(
            records, action, version=version, key=key, client=provider, with_status=True
        )
        assert status == 200 and completed.resulting_version == version + 1
        db.expire_all()
        ended_at = db.get(InterviewSession, sessions[0].id).ended_at
        count_after = count(db, InterviewAgentTurn)
        # A replay is metadata-only, so this patched commit must not be invoked again.
        replay, replay_status = turn(
            records,
            action,
            version=version,
            key=key,
            client=provider,
            decision=UnavailableProcessingDecision(),
            with_status=True,
        )
        assert replay_status == 200 and replay == completed
        assert count(db, InterviewAgentTurn) == count_after == before_count + 1
        assert db.get(InterviewSession, sessions[0].id).ended_at == ended_at
        after = service.get_state(db, users[0].id, sessions[0].id)
        assert after.generation_epoch == state_before.generation_epoch + (action != "start")
    assert not provider.requests


@pytest.mark.parametrize("legacy_status", ["idle", "awaiting_answer", "ended"])
def test_active_legacy_session_all_states_allow_explicit_end_and_replay(records, legacy_status):
    db, _, sessions = records
    state = InterviewAgentState(
        session_id=sessions[0].id,
        contract_version="interview-agent.v1",
        status=legacy_status,
        version=5,
        generation_epoch=0,
        policy_version="legacy-unknown",
    )
    db.add(state)
    db.commit()
    key = uuid.uuid4()
    provider = SyntheticClient(db)
    ended = turn(
        records,
        "end",
        version=5,
        key=key,
        client=provider,
        decision=UnavailableProcessingDecision(),
    )
    assert ended.contract_version == CONTRACT_VERSION
    assert ended.result_state_contract_version == "interview-agent.v1"
    assert ended.resulting_status == "ended" and ended.resulting_version == 6
    assert state.contract_version == "interview-agent.v1" and state.generation_epoch == 1
    assert sessions[0].status == "completed" and sessions[0].ended_at is not None
    original_ended_at = db.scalar(
        select(InterviewSession.ended_at).where(InterviewSession.id == sessions[0].id)
    )
    replay, status = turn(
        records,
        "end",
        version=5,
        key=key,
        client=provider,
        decision=UnavailableProcessingDecision(),
        with_status=True,
    )
    assert status == 200 and replay == ended
    assert (
        db.scalar(select(InterviewSession.ended_at).where(InterviewSession.id == sessions[0].id))
        == original_ended_at
        and not provider.requests
    )


def test_v2_ended_state_with_active_session_rejects_new_end_key(records):
    db, _, sessions = records
    db.add(
        InterviewAgentState(
            session_id=sessions[0].id,
            contract_version=CONTRACT_VERSION,
            status="ended",
            version=2,
            generation_epoch=1,
            policy_version="synthetic-mock.v1",
        )
    )
    db.commit()
    assert_code("AGENT_STATE_CONFLICT", lambda: turn(records, "end", version=2))
    assert count(db, InterviewAgentTurn) == 0 and sessions[0].status == "active"


def test_inconsistent_v2_state_and_legacy_turn_fail_closed(records):
    db, users, sessions = records
    turn(records)
    db.add(
        InterviewAgentTurn(
            session_id=sessions[0].id,
            actor_user_id=users[0].id,
            idempotency_key=uuid.uuid4(),
            contract_version="interview-agent.v1",
            action="end",
            request_fingerprint=b"x" * 32,
            execution_status="completed",
            result_kind="control",
            result_state_contract_version="interview-agent.v1",
            resulting_version=1,
            resulting_status="ended",
        )
    )
    db.commit()
    assert_code("AGENT_STATE_UNAVAILABLE", lambda: turn(records, "end", version=1))
    assert sessions[0].status == "active"
    assert db.get(InterviewAgentState, sessions[0].id).contract_version == CONTRACT_VERSION


@pytest.mark.parametrize("committed", [False, True])
def test_discard_commit_uncertainty_returns_authoritative_state(records, monkeypatch, committed):
    db, _, _ = records
    turn(records)
    source = answer(records)
    key = uuid.uuid4()
    real_commit = db.commit

    def during(request):
        db.execute(
            update(InterviewMessage)
            .where(InterviewMessage.id == source.id)
            .values(content="合成来源发生变化")
        )
        real_commit()

        def uncertain():
            if committed:
                real_commit()
            raise RuntimeError("synthetic-discard-outcome")

        monkeypatch.setattr(db, "commit", uncertain)
        return result_for(request)

    provider = SyntheticClient(db, during)
    if committed:
        assert_code(
            "AGENT_RESULT_DISCARDED",
            lambda: turn(records, "request_question", version=1, key=key, client=provider),
        )
    else:
        result, status = turn(
            records, "request_question", version=1, key=key, client=provider, with_status=True
        )
        assert status == 202 and result.execution_status == "pending"
    db.expire_all()
    stored = db.get(InterviewAgentTurn, provider.requests[0].request_id)
    assert stored.execution_status == ("discarded" if committed else "pending")
    assert stored.output_scope_id is None and stored.output_message_id is None
    assert len(provider.requests) == 1
    if not committed:
        replay, status = turn(
            records, "request_question", version=1, key=key, client=provider, with_status=True
        )
        assert status == 202 and replay.id == stored.id and len(provider.requests) == 1


@pytest.mark.parametrize("operation", ["post", "get_turn"])
@pytest.mark.parametrize("foreign", [False, True])
def test_agent_cross_owner_mutation_and_turn_reads_are_fixed_404(records, operation, foreign):
    db, users, sessions = records
    owner_turn = turn(records)
    before = count(db, InterviewAgentTurn)
    provider = SyntheticClient(db)
    target_session = sessions[0].id if foreign else uuid.uuid4()
    if operation == "get_turn":
        callback = lambda: service.get_turn(db, users[1].id, target_session, owner_turn.id)
    else:
        callback = lambda: service.advance(
            db,
            users[1].id,
            target_session,
            AgentTurnCreate(
                contract_version=CONTRACT_VERSION, action="request_question", expected_version=1
            ),
            uuid.uuid4(),
            SyntheticDecision(),
            provider,
        )
    exc = assert_code("NOT_FOUND", callback)
    assert error_body(exc) == (
        404,
        {
            "success": False,
            "error": {"code": "NOT_FOUND", "message": "Resource not found", "details": None},
        },
    )
    assert not provider.requests and count(db, InterviewAgentTurn) == before


@pytest.mark.parametrize("change", ["source", "history", "permission"])
def test_no_question_cannot_complete_after_input_or_permission_changes(records, change):
    db, _, _ = records
    turn(records)
    source = answer(records)
    first = turn(records, "request_question", client=SyntheticClient(db))
    revoked = False

    class Decision:
        def require(self, **kwargs):
            if revoked:
                raise AppException("restricted", code="PROCESSING_DENIED", status_code=403)

    def during(request):
        nonlocal revoked
        if change == "permission":
            revoked = True
        else:
            target_id = source.id if change == "source" else first.output_message_id
            db.execute(
                update(InterviewMessage)
                .where(InterviewMessage.id == target_id)
                .values(content="合成内容已变化")
            )
            db.commit()
        return result_for(
            request, outcome="no_question", question_key=None, question=None, question_basis=None
        )

    provider = SyntheticClient(db, during)
    assert_code(
        "AGENT_RESULT_DISCARDED",
        lambda: turn(records, "request_question", client=provider, decision=Decision()),
    )
    stored = db.get(InterviewAgentTurn, provider.requests[0].request_id)
    assert stored.execution_status == "discarded" and stored.result_kind is None
    assert db.get(InterviewAgentState, first.session_id).version == 2
    assert (
        db.scalar(
            select(func.count())
            .select_from(InterviewMessage)
            .where(InterviewMessage.role == "assistant")
        )
        == 1
    )
