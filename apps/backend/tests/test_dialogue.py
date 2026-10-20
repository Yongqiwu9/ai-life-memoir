"""Synthetic service tests, in-memory SQLite and a separate pure C1 JSON fixture process.

No ASGI, listening socket, external provider, .env, provisioning or real database.
Run under the existing test_interview_agent.py isolation bootstrap.
"""

import copy
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.exceptions import AppException
from app.database import models_import  # noqa: F401
from app.database.base import Base
from app.models.dialogue_runtime import AgentCheckpoint, AgentContext, AgentEffect, AgentSource
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.interview import Interview
from app.models.interview_agent import InterviewAgentState, InterviewAgentTurn
from app.models.interview_message import InterviewMessage
from app.models.interview_session import InterviewSession
from app.models.user import User
from app.schemas import dialogue as c
from app.services import dialogue as service
from app.services import dialogue_checkpoint as cp
from app.services.dialogue_policy import Integrity, Runtime, UnavailableAllocation


def observe_sql(db):
    """Capture statements, never parameters or source bodies."""
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower().strip())

    event.listen(db.get_bind(), "before_cursor_execute", record)
    return statements, record


def assert_metadata_only(statements):
    assert statements
    assert all(s.startswith("select") for s in statements)
    assert not any("sensitive_json" in s or "interview_messages.content" in s for s in statements)


class Allocation:
    def __init__(self, actor, session):
        self.actor, self.session, self.time = actor, session, 0

    def require(self, actor, session):
        if (actor, session) != (self.actor, self.session):
            raise AppException("Denied", code="PROCESSING_DENIED", status_code=403)

    def elapsed_ms(self, session):
        assert session == self.session
        return self.time


class KernelClient:
    """Separate app namespace; JSON-only fixture calls, no runtime cross-app import."""

    def __init__(self, db):
        self.db, self.calls, self.hook = db, [], None

    def call(self, request):
        assert not self.db.in_transaction()
        self.calls.append(request)
        if self.hook:
            self.hook(request)
        source = str(Path(__file__).resolve().parents[3] / "services/ai-service")
        code = (
            "import sys,os;os.environ.clear();"
            "sys.addaudithook(lambda e,a: (_ for _ in ()).throw(RuntimeError('NO_NETWORK')) if e.startswith('socket.') else None);"
            "sys.path.insert(0,sys.argv[1]);"
            "from app.dialogue.wire import WireRequest;"
            "from app.dialogue.service import execute;"
            "from app.dialogue.mock import DeterministicDialogueMock;"
            "r=execute(WireRequest.model_validate_json(sys.stdin.buffer.read()),DeterministicDialogueMock());"
            "sys.stdout.buffer.write(r.model_dump_json().encode('utf-8'))"
        )
        process = subprocess.Popen(
            [sys.executable, "-I", "-B", "-c", code, source],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:/Windows")},
        )
        try:
            output, errors = process.communicate(request.model_dump_json().encode(), timeout=20)
        except subprocess.TimeoutExpired:
            # No arbitrary termination or silent rerun; preserve identity for investigation.
            raise AssertionError(
                f"Pure fixture process exit UNKNOWN; retained PID {process.pid}"
            ) from None
        assert process.returncode == 0, errors.decode("utf-8", errors="replace")
        return c.WireReply.model_validate_json(output)


@pytest.fixture
def graph():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as db:
        owner = User(email="dialogue-synthetic@example.com", password_hash="synthetic")
        stranger = User(email="dialogue-stranger@example.com", password_hash="synthetic")
        db.add_all([owner, stranger])
        db.flush()
        family = Family(owner_id=owner.id, name="Synthetic family")
        db.add(family)
        db.flush()
        member = FamilyMember(family_id=family.id, name="Synthetic subject")
        db.add(member)
        db.flush()
        interview = Interview(family_member_id=member.id, title="Synthetic interview")
        db.add(interview)
        db.flush()
        session = InterviewSession(interview_id=interview.id, status="active")
        db.add(session)
        db.commit()
        actor, other, session_id = owner.id, stranger.id, session.id
        db.rollback()
        allocation = Allocation(actor, session_id)
        policy = c.Policy(
            version="synthetic-test.v1",
            complete_pause_ms=5,
            uncertain_pause_ms=10,
            max_events=200,
            max_sources=50,
            max_context_chars=100_000,
            max_history_items=10,
            max_summary_entries=50,
            mode="light",
        )
        runtime = Runtime(
            allocation, policy, Integrity({"synthetic-v1": b"s" * 32}, "synthetic-v1"), 1000
        )
        yield db, actor, other, session_id, runtime, KernelClient(db)
    engine.dispose()


def command(graph, action, *, apply=True, **extra):
    db, actor, _, session_id, runtime, client = graph
    state = db.get(InterviewAgentState, session_id)
    version = state.persistence_version if state else 0
    result = service.submit(
        db,
        actor,
        session_id,
        c.CommandCreate(action=action, expected_version=version, **extra),
        uuid.uuid4(),
        runtime,
    )
    return (
        service.apply(db, actor, session_id, result.id, runtime, client)
        if apply and result.execution_status == "queued"
        else result
    )


def put_text(graph, content="合成故事：那天我记不清了。", *, apply=True):
    db, actor, _, session_id, runtime, client = graph
    version = service.read_state(db, actor, session_id, runtime).persistence_version
    result = service.save_text(
        db,
        actor,
        session_id,
        c.TextCreate(content=content, human_turn_id=uuid.uuid4(), expected_version=version),
        uuid.uuid4(),
        runtime,
    )
    return service.apply(db, actor, session_id, result.id, runtime, client) if apply else result


def question(graph):
    db, actor, _, session_id, runtime, client = graph
    result = command(graph, "request_response")
    effect = db.scalar(
        select(AgentEffect).where(
            AgentEffect.session_id == session_id,
            AgentEffect.kind == "generate",
            AgentEffect.status == "reserved",
        )
    )
    effect_id = effect.id
    db.rollback()
    service.dispatch(db, actor, session_id, effect_id, runtime, client)
    return result


def delivered(graph):
    db, actor, _, session_id, runtime, client = graph
    state = service.read_state(db, actor, session_id, runtime)
    assert state.ready_response_id and state.delivery_token
    response, token = state.ready_response_id, state.delivery_token
    start = service.deliver(
        db,
        actor,
        session_id,
        response,
        c.DeliveryCreate(expected_version=state.persistence_version, token=token),
        uuid.uuid4(),
        runtime,
        client,
    )
    current = service.read_state(db, actor, session_id, runtime)
    finish = service.deliver(
        db,
        actor,
        session_id,
        response,
        c.DeliveryCreate(expected_version=current.persistence_version, token=token),
        uuid.uuid4(),
        runtime,
        client,
        complete=True,
    )
    assert finish.command.execution_status == "completed"
    return start


def test_start_has_no_implicit_generation(graph):
    result = command(graph, "start")
    db, actor, _, session_id, runtime, client = graph
    assert result.execution_status == "completed"
    assert service.read_state(db, actor, session_id, runtime).effective_status == "listening"
    assert all(x.operation != "generate" for x in client.calls)
    assert db.scalar(select(func.count()).select_from(InterviewMessage)) == 0


def test_text_original_and_event_then_explicit_apply(graph):
    command(graph, "start")
    result = put_text(graph, apply=False)
    db, actor, _, session_id, runtime, client = graph
    assert result.execution_status == "queued" and result.message_id
    assert db.get(InterviewMessage, result.message_id).content == "合成故事：那天我记不清了。"
    turn = db.get(InterviewAgentTurn, result.id)
    assert "content" not in turn.command_payload
    count = len(client.calls)
    applied = service.apply(db, actor, session_id, result.id, runtime, client)
    assert applied.execution_status == "completed"
    replay = service.apply(db, actor, session_id, result.id, runtime, client)
    assert replay.id == applied.id and len(client.calls) == count + 1
    assert db.scalar(select(func.count()).select_from(InterviewMessage)) == 1


def test_two_manual_questions_without_new_text_refresh_once(graph):
    command(graph, "start")
    question(graph)
    first = delivered(graph)
    assert first.text
    db, _, _, session_id, _, _ = graph
    first_context_revision = db.get(AgentCheckpoint, session_id).context_revision
    question(graph)
    second = delivered(graph)
    assert second.text and second.text != first.text
    assert db.get(AgentCheckpoint, session_id).context_revision == first_context_revision + 1
    children = list(
        db.scalars(
            select(InterviewAgentTurn).where(InterviewAgentTurn.event_kind == "context_refresh")
        )
    )
    assert len(children) == 1 and children[0].execution_status == "completed"
    assert (
        db.scalar(
            select(func.count())
            .select_from(InterviewAgentTurn)
            .where(InterviewAgentTurn.execution_status == "preparing")
        )
        == 0
    )


def test_pause_outage_preserves_input_and_resume_does_not_generate(graph):
    command(graph, "start")
    pause = command(graph, "pause", apply=False)
    raw = put_text(graph, apply=False)
    db, actor, _, session_id, runtime, client = graph
    assert pause.id and raw.message_id
    assert service.read_state(db, actor, session_id, runtime).effective_status == "paused"
    result = command(graph, "resume")
    assert result.execution_status == "completed"
    assert db.get(InterviewMessage, raw.message_id).content
    assert all(x.operation != "generate" for x in client.calls)


def test_restricted_checkpoint_never_selects_sensitive_or_content(graph):
    command(graph, "start")
    put_text(graph)
    question(graph)
    db, actor, _, session_id, runtime, _client = graph
    source = db.scalar(select(AgentSource))
    service.restrict_source(db, actor, session_id, source.stable_message_id, runtime)
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    event.listen(db.get_bind(), "before_cursor_execute", record)
    try:
        state = service.read_state(db, actor, session_id, runtime)
        assert state.effective_status == "blocked"
        ended = command(graph, "end")
        assert ended.execution_status == "completed"
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", record)
    selected = [s for s in statements if s.lstrip().startswith("select")]
    assert not any("sensitive_json" in s or "interview_messages.content" in s for s in selected)
    assert db.scalar(select(AgentCheckpoint.sensitive_json)) is None


def test_cross_owner_and_default_allocation_denied(graph):
    db, actor, other, session_id, runtime, _ = graph
    with pytest.raises(AppException) as denied:
        service.submit(
            db,
            other,
            session_id,
            c.CommandCreate(action="start", expected_version=0),
            uuid.uuid4(),
            runtime,
        )
    assert denied.value.code == "NOT_FOUND"
    with pytest.raises(AppException):
        service.submit(
            db,
            actor,
            session_id,
            c.CommandCreate(action="start", expected_version=0),
            uuid.uuid4(),
            Runtime(UnavailableAllocation()),
        )
    assert db.scalar(select(func.count()).select_from(InterviewAgentState)) == 0


def test_same_key_replay_and_payload_conflict(graph):
    db, actor, _, session_id, runtime, _ = graph
    key = uuid.uuid4()
    data = c.CommandCreate(action="start", expected_version=0)
    first = service.submit(db, actor, session_id, data, key, runtime)
    assert service.submit(db, actor, session_id, data, key, runtime).id == first.id
    with pytest.raises(AppException) as conflict:
        service.submit(
            db, actor, session_id, c.CommandCreate(action="end", expected_version=0), key, runtime
        )
    assert conflict.value.code == "IDEMPOTENCY_CONFLICT"


@pytest.mark.parametrize("phase", ["ready", "active", "retired"])
def test_split_merge_exact_and_extra_leaf_rejected(graph, phase):
    command(graph, "start")
    question(graph)
    db, actor, _, session_id, runtime, _ = graph
    if phase == "active":
        ready = service.read_state(db, actor, session_id, runtime)
        service.deliver(
            db,
            actor,
            session_id,
            ready.ready_response_id,
            c.DeliveryCreate(
                expected_version=ready.persistence_version, token=ready.delivery_token
            ),
            uuid.uuid4(),
            runtime,
            graph[-1],
        )
    elif phase == "retired":
        delivered(graph)
    envelope = db.get(InterviewAgentState, session_id)
    state = cp.load(db, actor, envelope, runtime)
    metadata, sensitive = cp.split(state)
    assert "text" not in (metadata.get("ready_response") or {})
    assert cp.merge(metadata, sensitive) == state
    if phase == "retired":
        assert not sensitive["responses"]
        assert sensitive["questions"]  # Legitimate delivered question history survives.
    for bucket, leaves in sensitive.items():
        for name in leaves:
            missing = copy.deepcopy(sensitive)
            del missing[bucket][name]
            with pytest.raises(AppException) as caught:
                cp.merge(metadata, missing)
            assert caught.value.code == "DIALOGUE_CHECKPOINT_UNAVAILABLE"
    tampered = copy.deepcopy(sensitive)
    tampered["responses"]["orphan"] = {"text": "secret"}
    with pytest.raises(AppException):
        cp.merge(metadata, tampered)
    orphan_question = copy.deepcopy(sensitive)
    orphan_question["questions"][str(uuid.uuid4())] = "synthetic orphan"
    with pytest.raises(AppException):
        cp.merge(metadata, orphan_question)
    extra = copy.deepcopy(sensitive)
    extra["unexpected"] = {}
    with pytest.raises(AppException):
        cp.merge(metadata, extra)


def test_end_is_terminal_and_no_rpc(graph):
    command(graph, "start")
    db, actor, _, session_id, runtime, client = graph
    before = len(client.calls)
    command(graph, "end")
    assert len(client.calls) == before
    with pytest.raises(AppException):
        put_text(graph)
    assert service.read_state(db, actor, session_id, runtime).session_status == "completed"


def test_queued_apply_does_not_open_network_or_real_db(graph):
    db, _, _, _, _, _ = graph
    assert db.scalar(text("PRAGMA foreign_keys")) == 1
    assert db.get_bind().url.database in {None, "", ":memory:"}


def test_pure_transition_explicit_retry_preserves_event(graph):
    command(graph, "start")
    root = put_text(graph, apply=False)
    db, actor, _, session_id, runtime, client = graph
    failed = []

    def once(request):
        if request.event and request.event.payload.kind == "user_message_committed" and not failed:
            failed.append(request.event.model_dump_json())
            raise TimeoutError("synthetic pure transition outage")

    client.hook = once
    with pytest.raises(AppException) as caught:
        service.apply(db, actor, session_id, root.id, runtime, client)
    assert caught.value.code == "DIALOGUE_TRANSITION_PENDING"
    turn = db.get(InterviewAgentTurn, root.id)
    frozen = copy.deepcopy(turn.event_envelope)
    assert turn.execution_status == "preparing" and len(turn.transition_attempts) == 1
    runtime.allocation.time = 500
    db.expunge_all()  # Retry from persisted state, not the original identity-map objects.
    result = service.apply(db, actor, session_id, root.id, runtime, client)
    assert result.execution_status == "completed" and result.message_id == root.message_id
    calls = [
        x.event
        for x in client.calls
        if x.event and x.event.payload.kind == "user_message_committed"
    ]
    assert len(calls) == 2 and calls[0] == calls[1]
    assert frozen["event_id"] == str(calls[1].event_id)
    assert frozen == calls[1].model_dump(mode="json")
    assert calls[1].time_ms == calls[0].time_ms
    assert "Synthetic private narrative" not in json.dumps(frozen)
    assert db.scalar(select(func.count()).select_from(InterviewMessage)) == 1


def test_current_generation_unknown_blocks_all_new_generation(graph):
    command(graph, "start")
    command(graph, "request_response")
    db, actor, _, session_id, runtime, client = graph
    effect = db.scalar(select(AgentEffect).where(AgentEffect.kind == "generate"))
    effect_id = effect.id
    db.rollback()

    def timeout(request):
        if request.operation == "generate":
            raise TimeoutError("synthetic unknown")

    client.hook = timeout
    with pytest.raises(AppException) as caught:
        service.dispatch(db, actor, session_id, effect_id, runtime, client)
    assert caught.value.code == "DIALOGUE_GENERATION_UNKNOWN"
    assert service.read_state(db, actor, session_id, runtime).effective_status == "blocked"
    with pytest.raises(AppException):
        service.dispatch(db, actor, session_id, effect_id, runtime, client)
    with pytest.raises(AppException):
        command(graph, "request_response")
    assert sum(x.operation == "generate" for x in client.calls) == 1
    assert db.get(AgentEffect, effect_id).dispatch_outcome == "unknown"
    command(graph, "end")


def test_stop_first_old_unknown_does_not_block_new_generation(graph):
    command(graph, "start")
    command(graph, "request_response")
    db, actor, _, session_id, runtime, client = graph
    old = db.scalar(select(AgentEffect).where(AgentEffect.kind == "generate"))
    old_id = old.id
    db.rollback()
    new_ready = []

    def interrupted(request):
        if request.operation == "generate":
            client.hook = None
            command(graph, "pause")
            command(graph, "resume")
            question(graph)
            new_ready.append(service.read_state(db, actor, session_id, runtime).ready_response_id)
            db.rollback()
            raise TimeoutError("old call unknown after stop")

    client.hook = interrupted
    with pytest.raises(AppException):
        service.dispatch(db, actor, session_id, old_id, runtime, client)
    current = service.read_state(db, actor, session_id, runtime)
    assert current.effective_status == "ready" and current.ready_response_id == new_ready[0]
    old = db.get(AgentEffect, old_id)
    assert old.status == "discarded" and old.dispatch_outcome == "unknown"
    assert sum(x.operation == "generate" for x in client.calls) == 2


def test_checkpoint_sensitive_tamper_detected_after_gate(graph):
    command(graph, "start")
    question(graph)
    db, actor, _, session_id, runtime, _ = graph
    row = db.get(AgentCheckpoint, session_id)
    altered = copy.deepcopy(db.scalar(select(AgentCheckpoint.sensitive_json)))
    altered["responses"]["ready_response"]["text"] = "synthetic tampered response"
    row.sensitive_json = altered
    db.commit()
    # Metadata reconciliation never hydrates or validates corrupted body leaves.
    assert service.read_state(db, actor, session_id, runtime).effective_status == "ready"
    with pytest.raises(AppException) as caught:
        cp.load(db, actor, db.get(InterviewAgentState, session_id), runtime)
    assert caught.value.code == "DIALOGUE_INTEGRITY_FAILURE"


def test_public_apply_binds_key_and_payload_without_redispatch(graph):
    db, actor, _, session_id, runtime, client = graph
    start = command(graph, "start", apply=False)
    key = uuid.uuid4()
    data = c.ApplyCreate(expected_version=0)
    first = service.apply_command(db, actor, session_id, start.id, data, key, runtime, client)
    count = len(client.calls)
    second = service.apply_command(db, actor, session_id, start.id, data, key, runtime, client)
    assert first == second and len(client.calls) == count
    with pytest.raises(AppException) as caught:
        service.apply_command(
            db, actor, session_id, start.id, c.ApplyCreate(expected_version=1), key, runtime, client
        )
    assert caught.value.code == "IDEMPOTENCY_CONFLICT"


def test_context_child_preemption_returns_parent_identity(graph):
    command(graph, "start")
    put_text(graph)
    question(graph)
    delivered(graph)
    db, actor, _, session_id, runtime, client = graph
    parent = command(graph, "request_response", apply=False)

    def pause(request):
        if request.event and request.event.payload.kind == "replace_selection":
            client.hook = None
            command(graph, "pause")

    client.hook = pause
    result = service.apply(db, actor, session_id, parent.id, runtime, client)
    assert result.id == parent.id and result.execution_status == "discarded"
    assert db.get(InterviewAgentState, session_id).active_command_id is None
    assert service.read_state(db, actor, session_id, runtime).effective_status == "paused"


@pytest.mark.parametrize("stage", [1, 2, 3])
def test_input_atomic_rollback_each_write_boundary(graph, monkeypatch, stage):
    command(graph, "start")
    db, actor, _, session_id, runtime, _ = graph
    before = service.read_state(db, actor, session_id, runtime).persistence_version
    from app.crud import dialogue as dialogue_crud

    original_message = service.message_crud.create_message_flush
    original_add = dialogue_crud.add_flush
    reached = []

    def message_failure(*args, **kwargs):
        value = original_message(*args, **kwargs)
        if stage == 1:
            reached.append("message")
            raise RuntimeError("synthetic message write failure")
        return value

    def related_failure(session, row):
        result = original_add(session, row)
        if (stage == 2 and isinstance(row, AgentSource)) or (
            stage == 3 and isinstance(row, InterviewAgentTurn)
        ):
            reached.append("source" if stage == 2 else "turn")
            raise RuntimeError("synthetic related write failure")
        return result

    monkeypatch.setattr(service.message_crud, "create_message_flush", message_failure)
    monkeypatch.setattr(dialogue_crud, "add_flush", related_failure)
    with pytest.raises(RuntimeError):
        put_text(graph, apply=False)
    assert len(reached) == 1
    monkeypatch.setattr(service.message_crud, "create_message_flush", original_message)
    monkeypatch.setattr(dialogue_crud, "add_flush", original_add)
    assert db.scalar(select(func.count()).select_from(InterviewMessage)) == 0
    assert db.scalar(select(func.count()).select_from(AgentSource)) == 0
    assert service.read_state(db, actor, session_id, runtime).persistence_version == before


@pytest.mark.parametrize(
    "action,extra",
    [("pause", {}), ("set_mode", {"mode": "record_only"}), ("end", {})],
)
def test_idle_safety_actions_need_no_initialize_rpc(graph, action, extra):
    start = command(graph, "start", apply=False)
    db, actor, _, session_id, runtime, client = graph
    result = command(graph, action, apply=False, **extra)
    assert result.id and not client.calls
    if action == "pause":
        assert db.get(InterviewAgentTurn, start.id).execution_status == "discarded"
        assert service.read_state(db, actor, session_id, runtime).effective_status == "idle"
        assert command(graph, "start").execution_status == "completed"


@pytest.mark.parametrize("action", ["typing_started", "typing_ended", "resume", "request_response"])
def test_idle_forbidden_events_do_not_write_unappliable_commands(graph, action):
    command(graph, "start", apply=False)
    db, _, _, _, _, client = graph
    before = db.scalar(select(func.count()).select_from(InterviewAgentTurn))
    with pytest.raises(AppException) as caught:
        command(graph, action, apply=False)
    assert caught.value.code == "START_REQUIRED" and not client.calls
    assert db.scalar(select(func.count()).select_from(InterviewAgentTurn)) == before


def test_idle_record_only_is_synchronized_before_later_start(graph):
    command(graph, "start", apply=False)
    command(graph, "set_mode", mode="record_only", apply=False)
    result = command(graph, "start")
    db, actor, _, session_id, runtime, client = graph
    state = service.read_state(db, actor, session_id, runtime)
    assert result.execution_status == "completed" and state.effective_status == "listening"
    assert db.get(InterviewAgentState, session_id).effective_mode == "record_only"
    assert all(x.operation != "generate" for x in client.calls)


def test_event_journal_context_never_copies_original_text(graph):
    command(graph, "start")
    source = put_text(graph, content="Synthetic private narrative")
    db, _, _, _, _, _ = graph
    row = db.get(InterviewAgentTurn, source.id)
    assert "Synthetic private narrative" not in json.dumps(row.event_envelope)
    assert "Synthetic private narrative" not in json.dumps(row.command_payload)
    contexts = list(db.scalars(select(AgentContext)))
    assert contexts
    for row in contexts:
        for field in (row.source_order, row.history_order, row.quote_slices):
            assert "Synthetic private narrative" not in json.dumps(field)


@pytest.mark.parametrize(
    "label,finish",
    [
        ("topic", "complete"),
        ("person", "complete"),
        ("time", "complete"),
        ("uncertain", "complete"),
        ("conflict", "complete"),
        ("uncertain", "interrupted"),
    ],
)
def test_restart_context_preserves_summary_label_and_frozen_started_history(graph, label, finish):
    command(graph, "start")
    put_text(graph)
    question(graph)
    db, actor, _, session_id, runtime, client = graph
    ready = service.read_state(db, actor, session_id, runtime)
    service.deliver(
        db,
        actor,
        session_id,
        ready.ready_response_id,
        c.DeliveryCreate(expected_version=ready.persistence_version, token=ready.delivery_token),
        uuid.uuid4(),
        runtime,
        client,
    )
    envelope = db.get(InterviewAgentState, session_id)
    core = cp.load(db, actor, envelope, runtime)
    active_context = cp.restore_context(db, actor, core.scope, core.context_revision, runtime)
    source = active_context.sources[0]
    output = db.scalar(select(InterviewMessage).where(InterviewMessage.role == "assistant"))
    snapshot = cp.context_value(
        core.scope,
        core.context_revision + 10,
        uuid.uuid4(),
        core.manifest_version + 1,
        list(active_context.sources),
        [
            *active_context.recent_history,
            c.HistoryItem(
                sequence=output.sequence,
                role="assistant",
                text=output.content,
                response_id=ready.ready_response_id,
                delivery="started",
            ),
        ],
        [
            c.SummaryEntry(
                label=label,
                quote=c.SourceQuote(ref=source.ref, start=0, end=2, text=source.text[:2]),
            )
        ],
        [],
        [],
    )
    cp.pin_context(db, snapshot)
    db.commit()
    if finish == "complete":
        current = service.read_state(db, actor, session_id, runtime)
        service.deliver(
            db,
            actor,
            session_id,
            ready.ready_response_id,
            c.DeliveryCreate(
                expected_version=current.persistence_version, token=ready.delivery_token
            ),
            uuid.uuid4(),
            runtime,
            client,
            complete=True,
        )
    else:
        command(graph, "pause")
    db.expunge_all()
    restored = cp.restore_context(db, actor, core.scope, snapshot.context_revision, runtime)
    assert restored == snapshot and restored.recent_history[-1].delivery == "started"
    assert restored.summary_entries[0].label == label
    assert cp.merge(*cp.split(core)) == core


# C2-IR-T01: force delivery between callback publication and dispatch return.
def test_generation_and_delivery_publish_atomically(graph, monkeypatch):
    command(graph, "start")
    db, _actor, _, session_id, _runtime, _client = graph
    committed = service._commit
    observed = []

    def after_callback_commit(session, who, sid, turn_id):
        value = committed(session, who, sid, turn_id)
        turn = session.get(InterviewAgentTurn, turn_id)
        publish = turn.event_kind == "response_ready" and turn.execution_status == "completed"
        session.rollback()
        if publish and not observed:
            generated = session.scalar(
                select(AgentEffect).where(
                    AgentEffect.session_id == sid, AgentEffect.kind == "generate"
                )
            )
            assert generated.status == "ready" and generated.response_id is not None
            generated_id = generated.id
            session.rollback()
            observed.append(generated_id)
            delivered(graph)
            assert (
                session.get(AgentEffect, generated_id, populate_existing=True).status == "completed"
            )
            session.rollback()
        return value

    monkeypatch.setattr(service, "_commit", after_callback_commit)
    question(graph)
    assert len(observed) == 1
    assert db.get(AgentEffect, observed[0], populate_existing=True).status == "completed"
    db.rollback()
    second = command(graph, "request_response")
    assert second.execution_status == "completed"
    assert (
        db.scalar(
            select(func.count())
            .select_from(AgentEffect)
            .where(
                AgentEffect.session_id == session_id,
                AgentEffect.kind == "generate",
                AgentEffect.status == "reserved",
            )
        )
        == 1
    )


@pytest.mark.parametrize(
    "control,extra", [("typing_started", {}), ("set_mode", {"mode": "record_only"})]
)
@pytest.mark.parametrize("phase", ["queued", "inflight"])
def test_pending_pause_survives_later_safety_control(graph, control, extra, phase):
    command(graph, "start")
    db, actor, _, session_id, runtime, client = graph
    pause = command(graph, "pause", apply=False)
    later = []

    def submit_later():
        later.append(command(graph, control, apply=False, **extra))
        assert (
            db.get(InterviewAgentTurn, pause.id, populate_existing=True).execution_status
            == "queued"
        )
        assert service.read_state(db, actor, session_id, runtime).effective_status == "paused"
        db.rollback()

    if phase == "queued":
        submit_later()
    else:

        def during_pause(request):
            if request.event and request.event.kind == "pause":
                client.hook = None
                submit_later()

        client.hook = during_pause
        result = service.apply(db, actor, session_id, pause.id, runtime, client)
        assert result.execution_status == "queued"
    expected = service.read_state(db, actor, session_id, runtime).persistence_version
    result = service.apply_command(
        db,
        actor,
        session_id,
        later[0].id,
        c.ApplyCreate(expected_version=expected),
        uuid.uuid4(),
        runtime,
        client,
    )
    assert result.execution_status == "completed"
    envelope = db.get(InterviewAgentState, session_id)
    core = cp.load(db, actor, envelope, runtime)
    assert core.status == envelope.status == "paused" and envelope.checkpoint_status == "valid"
    assert db.get(InterviewAgentTurn, pause.id).execution_status == "completed"
    if phase == "inflight":
        attempts = db.get(InterviewAgentTurn, pause.id).transition_attempts
        assert len(attempts) == 2 and attempts[0]["outcome"] == "superseded"
        assert attempts[0]["event_id"] != attempts[1]["event_id"]
    assert all(call.operation != "generate" for call in client.calls)
    assert db.scalar(select(func.count()).select_from(InterviewMessage)) == 0
    assert command(graph, "resume").execution_status == "completed"
    assert service.read_state(db, actor, session_id, runtime).effective_status == "listening"


def test_input_before_pending_pause_preserves_effective_pause_during_drain(graph, monkeypatch):
    command(graph, "start")
    raw = put_text(graph, apply=False)
    pause = command(graph, "pause", apply=False)
    typing = command(graph, "typing_started", apply=False)
    db, actor, _, session_id, runtime, client = graph
    original = service._commit
    snapshots = []

    def observe(session, who, sid, turn_id):
        value = original(session, who, sid, turn_id)
        turn = session.get(InterviewAgentTurn, turn_id)
        if turn.id == raw.id and turn.execution_status == "completed":
            state = service.read_state(session, who, sid, runtime)
            snapshots.append((state.effective_status, state.checkpoint_sync))
        session.rollback()
        return value

    monkeypatch.setattr(service, "_commit", observe)
    result = service.apply(db, actor, session_id, typing.id, runtime, client)
    assert result.execution_status == "completed"
    assert snapshots == [("paused", "sync_required")]
    assert db.get(InterviewAgentTurn, pause.id).execution_status == "completed"
    assert db.get(InterviewAgentTurn, raw.id).execution_status == "completed"
    assert service.read_state(db, actor, session_id, runtime).effective_status == "paused"
    kinds = [x.event.kind for x in client.calls if x.event]
    assert kinds[-3:] == ["user_message_committed", "pause", "typing_started"]


def test_child_turn_null_reason_rejected_by_sqlite_check(graph):
    from sqlalchemy.exc import IntegrityError

    command(graph, "start")
    db, _, _, session_id, _, _ = graph
    root = db.scalar(select(InterviewAgentTurn).where(InterviewAgentTurn.session_id == session_id))
    values = {col.name: getattr(root, col.name) for col in InterviewAgentTurn.__table__.columns}
    values.update(
        id=uuid.uuid4(),
        idempotency_key=uuid.uuid4(),
        event_id=uuid.uuid4(),
        command_order=root.command_order + 10,
        action="context_refresh",
        event_kind="context_refresh",
        parent_turn_id=root.id,
        internal_reason=None,
        execution_status="queued",
        finished_at=None,
        result_kind=None,
        result_state_contract_version=None,
        resulting_version=None,
        resulting_status=None,
        applied_event_seq=None,
        reserved_event_seq=None,
        reserved_persistence_version=None,
        reserved_stop_fence=None,
        event_envelope=None,
        transition_attempts=[],
        result_metadata=None,
    )
    with pytest.raises(IntegrityError, match="ck_dialogue_turn_profile"), db.begin_nested():
        db.add(InterviewAgentTurn(**values))
        db.flush()
    assert db.scalar(select(func.count()).select_from(InterviewAgentTurn)) == 1


def test_live_output_requires_stable_id_in_sqlite_check(graph):
    from sqlalchemy import update
    from sqlalchemy.exc import IntegrityError

    command(graph, "start")
    question(graph)
    delivered(graph)
    db, _, _, _, _, _ = graph
    effect = db.scalar(select(AgentEffect).where(AgentEffect.kind == "deliver"))
    effect_id, stable_id = effect.id, effect.output_stable_id
    assert stable_id and effect.output_message_id == stable_id
    with pytest.raises(IntegrityError, match="ck_dialogue_output_identity"), db.begin_nested():
        db.execute(
            update(AgentEffect).where(AgentEffect.id == effect_id).values(output_stable_id=None)
        )
    assert db.get(AgentEffect, effect_id, populate_existing=True).output_stable_id == stable_id


def test_remediated_null_checks_match_self_contained_migration():
    import ast

    source = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/c296a4e8d102_session_text_dialogue.py"
    )
    tree = ast.parse(source.read_text(encoding="utf-8"))
    up = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "UPGRADE_SQL"
    )
    for table, name in [
        (InterviewAgentTurn.__table__, "ck_dialogue_turn_profile"),
        (AgentEffect.__table__, "ck_dialogue_output_identity"),
    ]:
        constraint = next(x for x in table.constraints if x.name == name)
        statement = f"CONSTRAINT {name} CHECK ({constraint.sqltext})"
        assert sum(statement in row for row in up) == 1


@pytest.mark.parametrize("phase", ["queued", "inflight"])
def test_repeated_pause_revokes_unpublished_resume_without_new_core_event(graph, phase):
    command(graph, "start")
    command(graph, "pause")
    db, actor, _, session_id, runtime, client = graph
    resume = command(graph, "resume", apply=False)
    stopped = []

    def stop_again():
        before = service.read_state(db, actor, session_id, runtime)
        result = command(graph, "pause")
        after = service.read_state(db, actor, session_id, runtime)
        assert result.execution_status == "completed" and result.code == "ALREADY_STOPPED"
        assert (after.persistence_version, after.core_version, after.stop_fence) == (
            before.persistence_version,
            before.core_version,
            before.stop_fence,
        )
        assert after.effective_status == "paused" and after.checkpoint_sync == "valid"
        stopped.append(result.id)
        db.rollback()

    if phase == "queued":
        stop_again()
        result = service.apply(db, actor, session_id, resume.id, runtime, client)
    else:

        def during_resume(request):
            if request.event and request.event.kind == "resume":
                client.hook = None
                stop_again()

        client.hook = during_resume
        result = service.apply(db, actor, session_id, resume.id, runtime, client)
    assert len(stopped) == 1 and result.execution_status == "discarded"
    assert service.read_state(db, actor, session_id, runtime).effective_status == "paused"
    core = cp.load(db, actor, db.get(InterviewAgentState, session_id), runtime)
    assert core.status == "paused" and core.last_seq == 2
    assert db.get(InterviewAgentState, session_id).active_command_id is None
    if phase == "inflight":
        assert (
            db.get(InterviewAgentTurn, resume.id).transition_attempts[-1]["outcome"] == "superseded"
        )
    assert all(call.operation != "generate" for call in client.calls)
    assert db.scalar(select(func.count()).select_from(InterviewMessage)) == 0
    # Only a later explicit fresh resume may release the pause.
    assert command(graph, "resume").execution_status == "completed"
    assert service.read_state(db, actor, session_id, runtime).effective_status == "listening"


# Minimal supplement S02/S03: metadata refusal precedes body hydration;
# fingerprint failures are deliberately checked after an authorized body read.
@pytest.mark.parametrize("damage", ["restricted", "unlinked", "missing_binding"])
def test_source_metadata_failure_precedes_sensitive_select(graph, damage, monkeypatch):

    command(graph, "start")
    put_text(graph)
    db, actor, _, sid, runtime, client = graph
    envelope = db.get(InterviewAgentState, sid)
    source = db.scalar(select(AgentSource))
    if damage == "restricted":
        source.availability = "restricted"
    elif damage == "unlinked":
        source.live_message_id = None
    else:
        monkeypatch.setattr(cp.crud, "sources", lambda session, session_id: [])
    db.commit()
    count = len(client.calls)
    statements, listener = observe_sql(db)
    try:
        with pytest.raises(AppException) as caught:
            cp.load(db, actor, envelope, runtime)
        assert caught.value.code == "SOURCE_UNAVAILABLE"
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", listener)
    assert_metadata_only(statements)
    assert len(client.calls) == count


@pytest.mark.parametrize("role", ["user", "assistant"])
def test_context_body_fingerprint_change_rejects_without_rpc(graph, role):
    command(graph, "start")
    put_text(graph)
    question(graph)
    delivered(graph)
    command(graph, "request_response")  # Pin history containing delivered assistant.
    db, actor, _, sid, runtime, client = graph
    core = cp.load(db, actor, db.get(InterviewAgentState, sid), runtime)
    context = cp.restore_context(db, actor, core.scope, core.context_revision, runtime)
    assert any(item.role == role for item in context.recent_history)
    message = db.scalar(select(InterviewMessage).where(InterviewMessage.role == role))
    message.content = "synthetic altered body"
    db.commit()
    count = len(client.calls)
    statements, listener = observe_sql(db)
    try:
        with pytest.raises(AppException) as caught:
            cp.restore_context(db, actor, core.scope, core.context_revision, runtime)
        assert caught.value.code == "SOURCE_UNAVAILABLE"
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", listener)
    assert any("interview_messages.content" in s for s in statements)
    assert len(client.calls) == count


@pytest.mark.parametrize("entry", ["text", "transcript", "old_agent"])
def test_old_writers_cannot_bypass_dialogue_profile(graph, entry, monkeypatch):
    from app.schemas.interview_agent import AgentTurnCreate
    from app.schemas.interview_message import InterviewMessageCreate
    from app.services import interview_agent, interview_message

    command(graph, "start")
    db, actor, _, sid, _, client = graph
    before = len(client.calls)

    def forbidden(*args, **kwargs):
        pytest.fail("Legacy path reached source lookup or write before profile refusal")

    monkeypatch.setattr(interview_message.message_crud, "create_message_flush", forbidden)
    monkeypatch.setattr(interview_message.segment_service, "get_segment_for_session", forbidden)
    with pytest.raises(AppException) as caught:
        if entry == "text":
            interview_message.create_message(
                db,
                user_id=actor,
                session_id=sid,
                data=InterviewMessageCreate(content="synthetic legacy input"),
            )
        elif entry == "transcript":
            interview_message.create_transcript_message(
                db,
                user_id=actor,
                session_id=sid,
                segment_id=uuid.uuid4(),
            )
        else:
            interview_agent.advance(
                db,
                actor,
                sid,
                AgentTurnCreate(
                    contract_version="interview-agent.v2", action="start", expected_version=0
                ),
                uuid.uuid4(),
                None,
                client,
            )
    assert caught.value.code == (
        "AGENT_STATE_CONFLICT" if entry == "old_agent" else "DIALOGUE_WRITE_REQUIRED"
    )
    assert db.scalar(select(func.count()).select_from(InterviewMessage)) == 0
    assert len(client.calls) == before


def test_logical_clock_restart_and_stale_version(graph):
    command(graph, "start")
    db, actor, _, sid, runtime, client = graph
    runtime.allocation.time = 100
    first = put_text(graph)
    frozen = db.get(InterviewAgentTurn, first.id).event_envelope
    runtime.allocation.time = 1
    db.expunge_all()
    put_text(graph)
    events = [r.event for r in client.calls if r.event and r.event.kind == "user_message_committed"]
    assert events[-1].time_ms == events[-2].time_ms == frozen["time_ms"] == 100
    before = len(client.calls)
    with pytest.raises(AppException) as caught:
        service.submit(
            db,
            actor,
            sid,
            c.CommandCreate(action="request_response", expected_version=0),
            uuid.uuid4(),
            runtime,
        )
    assert caught.value.code == "DIALOGUE_VERSION_CONFLICT"
    assert len(client.calls) == before
    assert all(r.operation != "generate" for r in client.calls)


def test_rotated_key_replay_requires_original_key_and_exact_payload(graph):
    db, actor, _, sid, runtime, client = graph
    key = uuid.uuid4()
    data = c.CommandCreate(action="start", expected_version=0)
    original = service.submit(db, actor, sid, data, key, runtime)
    service.apply(db, actor, sid, original.id, runtime, client)
    rotated = Runtime(
        runtime.allocation,
        runtime.policy,
        Integrity({"synthetic-v1": b"s" * 32, "synthetic-v2": b"n" * 32}, "synthetic-v2"),
        1000,
    )
    count = len(client.calls)
    assert service.submit(db, actor, sid, data, key, rotated).id == original.id
    with pytest.raises(AppException) as caught:
        service.submit(
            db, actor, sid, c.CommandCreate(action="end", expected_version=0), key, rotated
        )
    assert caught.value.code == "IDEMPOTENCY_CONFLICT"
    without_old = Runtime(
        runtime.allocation,
        runtime.policy,
        Integrity({"synthetic-v2": b"n" * 32}, "synthetic-v2"),
        1000,
    )
    with pytest.raises(AppException) as caught:
        service.submit(db, actor, sid, data, key, without_old)
    assert caught.value.code == "DIALOGUE_INTEGRITY_UNAVAILABLE"
    assert len(client.calls) == count


@pytest.mark.parametrize(
    "kind", ["missing", "foreign_actor", "wrong_profile", "terminal", "corrupt_body"]
)
def test_command_readback_is_metadata_only_without_repair(graph, kind, monkeypatch):
    from types import SimpleNamespace

    command(graph, "start")
    db, actor, other, sid, _runtime, client = graph
    root = put_text(graph, apply=False)
    target = root.id
    turn = db.get(InterviewAgentTurn, target)
    if kind == "missing":
        target = uuid.uuid4()
    elif kind == "foreign_actor":
        turn.actor_user_id = other
    elif kind == "wrong_profile":
        original_turn = service.crud.turn

        def corrupt_metadata(*args, **kwargs):
            item = original_turn(*args, **kwargs)
            assert item.id == target
            return SimpleNamespace(actor_user_id=item.actor_user_id, integration_profile=None)

        monkeypatch.setattr(service.crud, "turn", corrupt_metadata)
    elif kind == "terminal":
        command(graph, "end")
    else:
        row = db.get(AgentCheckpoint, sid)
        row.sensitive_json = {"synthetic": "corrupt"}
    db.commit()
    count = len(client.calls)
    statements, listener = observe_sql(db)
    try:
        if kind in {"missing", "foreign_actor", "wrong_profile"}:
            with pytest.raises(AppException) as caught:
                service.read_command(db, actor, sid, target)
            assert caught.value.code == "COMMAND_OUTCOME_UNKNOWN"
        else:
            result = service.read_command(db, actor, sid, target)
            assert result.id == root.id
            assert result.execution_status == ("discarded" if kind == "terminal" else "queued")
            assert result.message_id == root.message_id
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", listener)
    assert_metadata_only(statements)
    assert len(client.calls) == count
    if kind == "terminal":
        assert db.get(InterviewMessage, root.message_id).content
        assert not db.get(InterviewAgentTurn, root.id).transition_attempts


def test_old_completion_cannot_mutate_new_response(graph):
    command(graph, "start")
    question(graph)
    db, actor, _, sid, runtime, client = graph
    old = service.read_state(db, actor, sid, runtime)
    delivered(graph)
    question(graph)
    fresh = service.read_state(db, actor, sid, runtime)
    count = len(client.calls)
    with pytest.raises(AppException) as caught:
        service.deliver(
            db,
            actor,
            sid,
            old.ready_response_id,
            c.DeliveryCreate(expected_version=fresh.persistence_version, token=old.delivery_token),
            uuid.uuid4(),
            runtime,
            client,
            complete=True,
        )
    assert caught.value.code == "DIALOGUE_DELIVERY_UNAVAILABLE"
    assert service.read_state(db, actor, sid, runtime) == fresh
    assert len(client.calls) == count


def test_child_key_collision_never_adopts_client_command(graph):
    command(graph, "start")
    question(graph)
    delivered(graph)
    db, actor, _, sid, runtime, client = graph
    parent = command(graph, "request_response", apply=False)
    state = service.read_state(db, actor, sid, runtime)
    collision = service.submit(
        db,
        actor,
        sid,
        c.CommandCreate(action="request_response", expected_version=state.persistence_version),
        uuid.uuid5(parent.id, "context_refresh"),
        runtime,
    )
    before = len(client.calls)
    with pytest.raises(AppException) as caught:
        service.apply(db, actor, sid, parent.id, runtime, client)
    assert caught.value.code == "IDEMPOTENCY_CONFLICT"
    child = db.get(InterviewAgentTurn, collision.id)
    assert child.parent_turn_id is None and child.event_kind == "request_response"
    assert child.execution_status == "queued" and len(client.calls) == before


def test_unchanged_context_has_no_refresh_or_revision_increment(graph):
    command(graph, "start")
    db, actor, _, sid, runtime, client = graph
    core = cp.load(db, actor, db.get(InterviewAgentState, sid), runtime)
    command(graph, "request_response")
    after = cp.load(db, actor, db.get(InterviewAgentState, sid), runtime)
    assert after.context_revision == core.context_revision
    assert (
        db.scalar(
            select(func.count())
            .select_from(InterviewAgentTurn)
            .where(InterviewAgentTurn.event_kind == "context_refresh")
        )
        == 0
    )
    assert all(r.operation != "generate" for r in client.calls)


def test_old_silence_cycle_does_not_generate_after_new_activity(graph):
    command(graph, "start")
    put_text(graph)
    db, actor, _, sid, runtime, client = graph
    before = cp.load(db, actor, db.get(InterviewAgentState, sid), runtime)
    runtime.allocation.time = 100
    old = service.submit_silence(db, actor, sid, runtime)
    assert (
        db.get(InterviewAgentTurn, old.id).command_payload["silence_cycle"] == before.silence_cycle
    )
    put_text(graph, content="Synthetic second human turn")
    db.expunge_all()
    current = cp.load(db, actor, db.get(InterviewAgentState, sid), runtime)
    assert current.silence_cycle > before.silence_cycle
    count = len(client.calls)
    result = service.apply(db, actor, sid, old.id, runtime, client)
    assert result.execution_status == "discarded" and len(client.calls) == count
    assert all(request.operation != "generate" for request in client.calls)
