"""Allocated PostgreSQL 16.15 only; Runner never provisions or migrates.

Every case has unique graph IDs. Competing workers use independent committed
connections; only exact case rows are removed after all worker exits are known.
"""

import copy
import json
import os
import re
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, delete, event, func, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.models.dialogue_runtime import AgentCheckpoint, AgentEffect
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.interview import Interview
from app.models.interview_agent import InterviewAgentState, InterviewAgentTurn
from app.models.interview_message import InterviewMessage
from app.models.interview_session import InterviewSession
from app.models.user import User
from app.schemas import dialogue as c
from app.services import dialogue as service
from app.services.dialogue_policy import Integrity, Runtime
from tests.test_dialogue import Allocation, KernelClient, command, delivered, put_text, question

pytestmark = pytest.mark.integration

_RETAINED = []  # Keep connections/threads alive; never GC-close uncertain work.


class RunGuard:
    """Test-only SQL/teardown gate; actual driver UNKNOWN is never a mock outcome."""

    def __init__(self, request, raw):
        self.request, self.url = request, make_url(raw)
        self.unknown = False
        self.handles = []
        self.resources = []
        self.listeners = []

    def retain(self, category):
        if self.unknown:
            return
        self.unknown = True
        self.request.session.shouldstop = "Actual dialogue resource UNKNOWN; retained"
        _RETAINED.append(self)
        receipt = os.environ.get("DIALOGUE_RETENTION_RECEIPT")
        if receipt:
            try:
                target = Path(receipt)
                if target.is_symlink() or not target.parent.is_dir() or target.exists():
                    raise RuntimeError("Retention receipt target invalid")
                with target.open("x", encoding="utf-8") as stream:
                    json.dump(
                        {
                            "state": "RETAINED",
                            "run": os.environ["DIALOGUE_ALLOCATION_RUN_ID"],
                            "category": category,
                        },
                        stream,
                    )
                    stream.flush()
                    os.fsync(stream.fileno())
                return
            except Exception:  # noqa: BLE001 - receipt failure must not authorize cleanup
                self.receipt_failed = True
        # Existing CI Manager cannot read a new local receipt. Keep its child
        # non-quiescent so its existing timeout/group gate retains allocation.
        sentinel = threading.Thread(target=threading.Event().wait, daemon=False)
        self.handles.append(sentinel)
        sentinel.start()

    def matches(self, connection):
        url = connection.engine.url
        return (url.database, url.host, url.port) == (
            self.url.database,
            self.url.host,
            self.url.port,
        )

    def check(self, connection=None, *_args):
        if self.unknown and (connection is None or self.matches(connection)):
            raise RuntimeError("Actual dialogue resource UNKNOWN; SQL prohibited")

    def install(self):
        def sql_guard(connection, *_args):
            self.check(connection)

        def driver_error(context):
            if context.engine and self.matches(SimpleNamespace(engine=context.engine)):
                code = getattr(context.original_exception, "sqlstate", None)
                if context.is_disconnect or not code or code.startswith(("08", "57P", "58")):
                    self.retain("driver_outcome_unknown")

        for name, callback in (
            ("before_cursor_execute", sql_guard),
            ("commit", sql_guard),
            ("rollback", sql_guard),
            ("handle_error", driver_error),
        ):
            event.listen(Engine, name, callback)
            self.listeners.append((name, callback))
        guard = self

        class StopAfterFailure:
            @pytest.hookimpl(hookwrapper=True)
            def pytest_runtest_makereport(self, item, call):
                outcome = yield
                report = outcome.get_result()
                if item is guard.request.node and report.failed:
                    guard.request.session.shouldstop = "Dialogue case failed; stop next case"
                    if call.excinfo and "Pure fixture process exit UNKNOWN; retained PID" in str(
                        call.excinfo.value
                    ):
                        guard.retain("fixture_process_unknown")

        self.plugin = StopAfterFailure()
        self.request.config.pluginmanager.register(self.plugin)

    def finish(self):
        if any(handle.is_alive() for handle in self.handles):
            self.retain("worker_exit_unknown")
        self.check()

    def uninstall(self):
        self.check()
        for name, callback in self.listeners:
            event.remove(Engine, name, callback)
        self.request.config.pluginmanager.unregister(self.plugin)

    @contextmanager
    def session(self, engine):
        db = Session(engine)
        self.resources.append(db)
        try:
            yield db
        finally:
            self.finish()
            db.close()


def hba_rejection(exc, *, host, port, client, role, database):
    """Connection failures may have no structured SQLSTATE; never invent one."""
    code = getattr(exc, "sqlstate", None)
    assert code in {None, "28000"}
    address = re.escape(host)
    reason = (
        r'FATAL:\s+pg_hba\.conf rejects connection for host "'
        + re.escape(client)
        + r'", user "'
        + re.escape(role)
        + r'", database "'
        + re.escape(database)
        + r'", (?:SSL encryption|no encryption)'
    )
    prefix = (
        r'(?:connection failed: )?(?:connection to server at "'
        + address
        + r'", port '
        + str(port)
        + r" failed: )?"
    )
    lines = [line.strip() for line in str(exc).splitlines() if line.strip()]
    assert 1 <= len(lines) <= 2 and all(re.fullmatch(prefix + reason, line) for line in lines)
    return {
        "category": "exact_hba_reject",
        "sqlstate": code,
        "client": client,
        "role": role,
        "database": database,
    }


def _connection_denial(raw, database, *, hba):
    """A valid-password positive control is required before each denial probe."""
    import psycopg

    url = make_url(raw)
    parameters = {
        "host": url.host,
        "port": url.port,
        "user": url.username,
        "password": url.password,
        "connect_timeout": 5,
        "passfile": os.devnull,
        "autocommit": True,
    }
    with psycopg.connect(**parameters, dbname=url.database) as positive:
        assert positive.execute("SELECT current_database(),current_user").fetchone() == (
            url.database,
            url.username,
        )
    try:
        with psycopg.connect(**parameters, dbname=database):
            pytest.fail("Runner connected outside its allocation")
    except psycopg.OperationalError as exc:
        # Refuse password errors, network failures, TLS failures and timeouts.
        if hba:
            proof = local_allocation(raw)
            hba_rejection(
                exc,
                host=url.host,
                port=url.port,
                client=proof["client_address"],
                role=url.username,
                database=database,
            )
        else:
            assert exc.sqlstate == "42501"


def local_allocation(raw):
    """Validate a Manager receipt plus live allocation identity, never a boolean bypass."""
    if os.environ.get("DIALOGUE_ISOLATION_PROFILE") != "local-hba.v1":
        raise pytest.UsageError("Unknown local isolation profile")
    path = Path(os.environ["DIALOGUE_ALLOCATION_RECEIPT"])
    if path.is_symlink():
        raise pytest.UsageError("Allocation receipt must not be a link")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    url = make_url(raw)
    assert url.port == 55432
    assert receipt["run"] == os.environ["DIALOGUE_ALLOCATION_RUN_ID"]
    assert (receipt["database"], receipt["runner"], receipt["port"]) == (
        url.database,
        url.username,
        url.port,
    )
    assert receipt["hba_verified"] is True and receipt["version"] == 160015
    assert receipt["historical_database"] == "ai_life_memoir_c3_test"
    return receipt


def allocation_url():
    fields = [
        os.environ.get(x)
        for x in (
            "DIALOGUE_ALLOCATION_RUN_ID",
            "DIALOGUE_ALLOCATED_DATABASE",
            "DIALOGUE_RUNNER_ROLE",
            "TEST_DATABASE_URL",
        )
    ]
    if not all(fields):
        raise pytest.UsageError("Dialogue tests require verified Manager allocation")
    run, database, runner, raw = fields
    try:
        run_id, url = uuid.UUID(run), make_url(raw)
    except (ValueError, TypeError):
        raise pytest.UsageError("Invalid dialogue allocation") from None
    if (
        database != "ai_memoir_dialogue_ci_test_" + run_id.hex
        or url.database != database
        or runner != "d_ci_runner_" + run_id.hex
        or url.username != runner
        or url.get_backend_name() != "postgresql"
        or url.host != "127.0.0.1"
        or not url.port
    ):
        raise pytest.UsageError("Dialogue allocation identity mismatch")
    return raw


@pytest.fixture
def pg(request):
    raw = allocation_url()
    profile = os.environ.get("DIALOGUE_ISOLATION_PROFILE", "ci-acl.v1")
    if profile not in {"ci-acl.v1", "local-hba.v1"}:
        raise pytest.UsageError("Unknown dialogue isolation profile")
    if profile == "local-hba.v1":
        local_allocation(raw)
    engine = create_engine(
        raw,
        pool_reset_on_return=None,
        connect_args={
            "connect_timeout": 5,
            "options": "-c statement_timeout=8000 -c lock_timeout=4000",
        },
    )
    guard = RunGuard(request, raw)
    guard.resources.append(engine)
    guard.install()
    with guard.session(engine) as db:
        assert int(db.scalar(text("SHOW server_version_num"))) == 160015
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "c296a4e8d102"
        privileges = db.execute(
            text(
                "SELECT rolsuper,rolcreatedb,rolcreaterole,rolbypassrls FROM pg_roles WHERE rolname=current_user"
            )
        ).one()
        assert not any(privileges)
        owner = User(email=f"dialogue-pg-{uuid.uuid4().hex}@example.com", password_hash="synthetic")
        db.add(owner)
        db.flush()
        family = Family(owner_id=owner.id, name="Synthetic allocated family")
        db.add(family)
        db.flush()
        member = FamilyMember(family_id=family.id, name="Synthetic subject")
        db.add(member)
        db.flush()
        interview = Interview(family_member_id=member.id, title="Synthetic allocated interview")
        db.add(interview)
        db.flush()
        session = InterviewSession(interview_id=interview.id, status="active")
        db.add(session)
        db.commit()
        actor, session_id, family_id = owner.id, session.id, family.id
        runtime = Runtime(
            Allocation(actor, session_id),
            c.Policy(
                version="synthetic-test.v1",
                complete_pause_ms=5,
                uncertain_pause_ms=10,
                max_events=200,
                max_sources=50,
                max_context_chars=100_000,
                max_history_items=10,
                max_summary_entries=50,
                mode="light",
            ),
            Integrity({"synthetic-v1": b"s" * 32}, "synthetic-v1"),
            1000,
        )
        graph = (db, actor, uuid.uuid4(), session_id, runtime, KernelClient(db))
        command(graph, "start")
        resource = SimpleNamespace(
            engine=engine, graph=graph, handles=guard.handles, safe=True, guard=guard
        )
        try:
            yield resource
        finally:
            if any(worker.is_alive() for worker in resource.handles):
                resource.safe = False
            if not resource.safe:
                guard.retain("worker_exit_unknown")
            guard.finish()
            db.rollback()
            db.execute(delete(Family).where(Family.id == family_id))
            db.execute(delete(User).where(User.id == actor))
            db.commit()
    engine.dispose()
    guard.uninstall()


def race(pg, left, right):
    barrier = threading.Barrier(2, timeout=5)
    results, failures = [], []

    def worker(fn):
        try:
            with Session(pg.engine) as db:
                barrier.wait()
                results.append(fn(db))
        except AppException as exc:
            failures.append(exc.code)
        except Exception as exc:  # noqa: BLE001 - test failures must reach main thread
            failures.append(type(exc).__name__)

    threads = [threading.Thread(target=worker, args=(fn,)) for fn in (left, right)]
    pg.handles.extend(threads)
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(15)
    if any(thread.is_alive() for thread in threads):
        pg.safe = False
        pytest.fail("Worker exit UNKNOWN; retained")
    return results, failures


def test_runtime_column_constraints(pg):
    db, actor, _, session_id, runtime, _ = pg.graph
    state = service.read_state(db, actor, session_id, runtime)
    assert state.effective_status == "listening" and state.checkpoint_sync == "valid"
    assert (
        db.scalar(
            text(
                "SELECT count(*) FROM pg_constraint WHERE conname='fk_dialogue_active_command' AND condeferrable"
            )
        )
        == 1
    )
    before = db.get(InterviewAgentState, session_id).persistence_version
    with pytest.raises(IntegrityError) as check, db.begin_nested():
        db.execute(
            text("UPDATE interview_agent_states SET persistence_version=-1 WHERE session_id=:id"),
            {"id": session_id},
        )
    assert check.value.orig.sqlstate == "23514"
    assert (
        db.get(InterviewAgentState, session_id, populate_existing=True).persistence_version
        == before
    )
    with pytest.raises(IntegrityError) as foreign_key, db.begin_nested():
        db.execute(text("SET CONSTRAINTS fk_dialogue_active_command IMMEDIATE"))
        db.execute(
            text(
                "UPDATE interview_agent_states SET active_command_id=:id WHERE session_id=:session"
            ),
            {"id": uuid.uuid4(), "session": session_id},
        )
    assert foreign_key.value.orig.sqlstate == "23503"
    assert db.get(InterviewAgentState, session_id, populate_existing=True).active_command_id is None
    root = db.scalar(select(InterviewAgentTurn).where(InterviewAgentTurn.session_id == session_id))
    duplicate = {
        column.name: getattr(root, column.name) for column in InterviewAgentTurn.__table__.columns
    }
    duplicate.update(id=uuid.uuid4(), idempotency_key=uuid.uuid4(), event_id=uuid.uuid4())
    with pytest.raises(IntegrityError) as unique, db.begin_nested():
        db.add(InterviewAgentTurn(**duplicate))
        db.flush()
    assert unique.value.orig.sqlstate == "23505"
    assert (
        db.scalar(
            select(func.count())
            .select_from(InterviewAgentTurn)
            .where(InterviewAgentTurn.session_id == session_id)
        )
        == 1
    )

    bad_child = dict(duplicate)
    bad_child.update(
        id=uuid.uuid4(),
        idempotency_key=uuid.uuid4(),
        event_id=uuid.uuid4(),
        command_order=root.command_order + 100,
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
    with pytest.raises(IntegrityError) as child_null, db.begin_nested():
        db.add(InterviewAgentTurn(**bad_child))
        db.flush()
    assert child_null.value.orig.sqlstate == "23514"
    assert child_null.value.orig.diag.constraint_name == "ck_dialogue_turn_profile"
    question(pg.graph)
    delivered(pg.graph)
    effect = db.scalar(
        select(AgentEffect).where(
            AgentEffect.session_id == session_id, AgentEffect.kind == "deliver"
        )
    )
    effect_id, stable_id = effect.id, effect.output_stable_id
    with pytest.raises(IntegrityError) as output_null, db.begin_nested():
        db.execute(
            text("UPDATE interview_agent_effects SET output_stable_id=NULL WHERE id=:id"),
            {"id": effect_id},
        )
    assert output_null.value.orig.sqlstate == "23514"
    assert output_null.value.orig.diag.constraint_name == "ck_dialogue_output_identity"
    assert db.get(AgentEffect, effect_id, populate_existing=True).output_stable_id == stable_id


def test_runner_is_restricted(pg):
    raw = allocation_url()
    profile = os.environ.get("DIALOGUE_ISOLATION_PROFILE", "ci-acl.v1")
    with pg.engine.connect() as connection:
        privileges = connection.execute(
            text(
                "SELECT rolsuper,rolcreatedb,rolcreaterole,rolbypassrls,rolreplication "
                "FROM pg_roles WHERE rolname=current_user"
            )
        ).one()
        assert not any(privileges)
        assert not connection.scalar(
            text(
                "SELECT has_database_privilege(current_user,current_database(),'CREATE') "
                "OR has_database_privilege(current_user,current_database(),'TEMP') "
                "OR has_schema_privilege(current_user,'public','CREATE')"
            )
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user)"
                )
            )
            == 0
        )
        if profile == "local-hba.v1":
            receipt = local_allocation(raw)
            actual = connection.execute(
                text(
                    "SELECT oid,datdba,shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"
                )
            ).one()
            assert tuple(actual) == (receipt["database_oid"], receipt["owner_oid"], receipt["run"])
            assert (
                connection.scalar(text("SELECT oid FROM pg_roles WHERE rolname=current_user"))
                == receipt["runner_oid"]
            )
        else:
            assert profile == "ci-acl.v1"
    if profile == "local-hba.v1":
        for database in ("postgres", "template1", "ai_life_memoir_c3_test"):
            _connection_denial(raw, database, hba=True)
        return
    # Preserve CI's stronger SQL ACL requirements, without a local-profile skip.
    with pg.engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT has_database_privilege(current_user,'postgres','CONNECT')")
            )
            is False
        )
        assert (
            connection.scalar(
                text("SELECT has_database_privilege(current_user,'template1','CONNECT')")
            )
            is False
        )


def test_parent_lock_sequence(pg):
    db, actor, _, session_id, runtime, _ = pg.graph
    version = service.read_state(db, actor, session_id, runtime).persistence_version
    db.rollback()
    waiting = threading.Event()
    results, failures, pids = [], [], []

    def writer():
        try:
            with Session(pg.engine) as worker:
                # Keep this transaction/connection until save_text acquires the lock.
                pids.append(worker.scalar(text("SELECT pg_backend_pid()")))
                waiting.set()
                results.append(
                    service.save_text(
                        worker,
                        actor,
                        session_id,
                        c.TextCreate(
                            content="Synthetic blocked writer",
                            human_turn_id=uuid.uuid4(),
                            expected_version=version,
                        ),
                        uuid.uuid4(),
                        runtime,
                    )
                )
        except BaseException as exc:  # noqa: BLE001 - report thread failure without raw details
            code = getattr(getattr(exc, "orig", exc), "sqlstate", None)
            failures.append(
                {
                    "exception_type": type(exc).__name__,
                    "sqlstate": code
                    if isinstance(code, str) and re.fullmatch(r"[0-9A-Z]{5}", code)
                    else None,
                }
            )

    thread = threading.Thread(target=writer)
    pg.handles.append(thread)
    started, ready, observed = False, False, False
    holder_pid, observation = None, None
    try:
        with pg.engine.begin() as holder:
            holder_pid = holder.scalar(text("SELECT pg_backend_pid()"))
            holder.execute(
                select(InterviewSession.id)
                .where(InterviewSession.id == session_id)
                .with_for_update()
            )
            thread.start()
            started = True
            ready = waiting.wait(5)
            if ready:
                assert len(pids) == 1 and pids[0] != holder_pid
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    with pg.engine.connect() as observer:
                        row = (
                            observer.execute(
                                text(
                                    "SELECT pid,wait_event_type,pg_blocking_pids(pid) AS blockers "
                                    "FROM pg_stat_activity WHERE pid=:pid"
                                ),
                                {"pid": pids[0]},
                            )
                            .mappings()
                            .first()
                        )
                    observation = dict(row) if row is not None else None
                    observed = (
                        observation is not None
                        and observation["wait_event_type"] == "Lock"
                        and holder_pid in observation["blockers"]
                    )
                    if observed:
                        break
                    time.sleep(0.02)
    finally:
        # The holder context releases its lock before this bounded join, even on failure.
        if started:
            thread.join(10)
            if thread.is_alive():
                pg.safe = False
                pg.guard.retain("worker_exit_unknown")
                pytest.fail("Worker exit UNKNOWN; retained")
    assert ready, {"code": "WRITER_NOT_READY", "failures": failures}
    assert not failures, {"code": "WRITER_FAILED", "failures": failures}
    assert observed, {
        "code": "PARENT_LOCK_WAIT_NOT_OBSERVED",
        "writer_pid": pids[0],
        "holder_pid": holder_pid,
        "last_observation": observation,
    }
    assert not thread.is_alive() and len(results) == 1
    assert (
        db.scalar(
            select(InterviewMessage.sequence).where(InterviewMessage.id == results[0].message_id)
        )
        == 1
    )


def test_parallel_same_key(pg):
    db, actor, _, session_id, runtime, _ = pg.graph
    version = service.read_state(db, actor, session_id, runtime).persistence_version
    db.rollback()
    key = uuid.uuid4()
    data = c.TextCreate(
        content="Synthetic exact replay", human_turn_id=uuid.uuid4(), expected_version=version
    )
    results, failures = race(
        pg,
        lambda d: service.save_text(d, actor, session_id, data, key, runtime),
        lambda d: service.save_text(d, actor, session_id, data, key, runtime),
    )
    assert not failures and len(results) == 2 and results[0].id == results[1].id
    assert (
        db.scalar(
            select(func.count())
            .select_from(InterviewMessage)
            .where(InterviewMessage.session_id == session_id)
        )
        == 1
    )


def test_normal_cas_race(pg):
    db, actor, _, session_id, runtime, _ = pg.graph
    a = command(pg.graph, "request_response", apply=False)
    b = command(pg.graph, "request_response", apply=False)
    results, failures = race(
        pg,
        lambda d: service.apply(d, actor, session_id, a.id, runtime, KernelClient(d)),
        lambda d: service.apply(d, actor, session_id, b.id, runtime, KernelClient(d)),
    )
    assert len(results) == 1 and failures
    assert (
        db.scalar(
            select(func.count())
            .select_from(AgentEffect)
            .where(AgentEffect.session_id == session_id, AgentEffect.kind == "generate")
        )
        == 1
    )


def generation_race(pg, stop):
    db, actor, _, session_id, runtime, _ = pg.graph
    command(pg.graph, "request_response")
    effect_id = db.scalar(
        select(AgentEffect.id).where(
            AgentEffect.session_id == session_id, AgentEffect.kind == "generate"
        )
    )
    db.rollback()
    entered, release = threading.Event(), threading.Event()
    outcome = []

    def worker():
        with Session(pg.engine) as d:
            client = KernelClient(d)
            client.hook = lambda request: (
                (entered.set(), release.wait(8)) if request.operation == "generate" else None
            )
            outcome.append(service.dispatch(d, actor, session_id, effect_id, runtime, client))

    thread = threading.Thread(target=worker)
    pg.handles.append(thread)
    thread.start()
    assert entered.wait(5)
    stop()
    release.set()
    thread.join(15)
    assert not thread.is_alive() and outcome
    assert (
        db.scalar(
            select(func.count())
            .select_from(InterviewMessage)
            .where(InterviewMessage.session_id == session_id, InterviewMessage.role == "assistant")
        )
        == 0
    )


def test_stop_publish_race(pg):
    generation_race(pg, lambda: command(pg.graph, "pause"))
    assert (
        service.read_state(pg.graph[0], pg.graph[1], pg.graph[3], pg.graph[4]).effective_status
        == "paused"
    )


def test_typing_delivery_race(pg):
    question(pg.graph)
    db, actor, _, session_id, runtime, _ = pg.graph
    ready = service.read_state(db, actor, session_id, runtime)
    db.rollback()
    entered, release = threading.Event(), threading.Event()
    outcomes = []

    def worker():
        with Session(pg.engine) as d:
            client = KernelClient(d)
            client.hook = lambda req: (
                (entered.set(), release.wait(8))
                if req.event and req.event.kind == "delivery_started"
                else None
            )
            outcomes.append(
                service.deliver(
                    d,
                    actor,
                    session_id,
                    ready.ready_response_id,
                    c.DeliveryCreate(
                        expected_version=ready.persistence_version, token=ready.delivery_token
                    ),
                    uuid.uuid4(),
                    runtime,
                    client,
                )
            )

    thread = threading.Thread(target=worker)
    pg.handles.append(thread)
    thread.start()
    assert entered.wait(5)
    command(pg.graph, "typing_started", apply=False)
    release.set()
    thread.join(15)
    assert not thread.is_alive() and outcomes and outcomes[0].text is None
    assert (
        db.scalar(
            select(func.count())
            .select_from(InterviewMessage)
            .where(InterviewMessage.session_id == session_id, InterviewMessage.role == "assistant")
        )
        == 0
    )


def test_claim_crash_once(pg):
    db, actor, _, session_id, runtime, client = pg.graph
    command(pg.graph, "request_response")
    effect_id = db.scalar(
        select(AgentEffect.id).where(
            AgentEffect.session_id == session_id, AgentEffect.kind == "generate"
        )
    )
    db.rollback()

    def fail(request):
        if request.operation == "generate":
            raise RuntimeError("synthetic lost reply")

    client.hook = fail
    with pytest.raises(AppException):
        service.dispatch(db, actor, session_id, effect_id, runtime, client)
    with pytest.raises(AppException):
        service.dispatch(db, actor, session_id, effect_id, runtime, client)
    assert sum(x.operation == "generate" for x in client.calls) == 1
    assert service.read_state(db, actor, session_id, runtime).effective_status == "blocked"


def test_delivery_unknown_readback(pg, monkeypatch):
    db, actor, _, session_id, runtime, client = pg.graph
    question(pg.graph)
    ready = service.read_state(db, actor, session_id, runtime)
    original = db.commit
    triggered = []
    outputs = []

    def remember_output(session, _context, _instances):
        outputs.extend(
            x.id for x in session.new if isinstance(x, InterviewMessage) and x.role == "assistant"
        )

    from sqlalchemy import event

    event.listen(db, "before_flush", remember_output)

    def ambiguous():
        original()
        if outputs and not triggered:
            triggered.append(True)
            raise RuntimeError("synthetic commit reply lost")

    monkeypatch.setattr(db, "commit", ambiguous)
    key = uuid.uuid4()
    data = c.DeliveryCreate(expected_version=ready.persistence_version, token=ready.delivery_token)
    service.deliver(db, actor, session_id, ready.ready_response_id, data, key, runtime, client)
    assert triggered == [True]
    service.deliver(db, actor, session_id, ready.ready_response_id, data, key, runtime, client)
    assert (
        db.scalar(
            select(func.count())
            .select_from(InterviewMessage)
            .where(InterviewMessage.session_id == session_id, InterviewMessage.role == "assistant")
        )
        == 1
    )


def test_source_publish_race(pg):
    put_text(pg.graph)
    db, actor, _, session_id, runtime, _ = pg.graph
    source = db.scalar(
        select(InterviewMessage.id).where(
            InterviewMessage.session_id == session_id, InterviewMessage.role == "user"
        )
    )
    db.rollback()
    generation_race(pg, lambda: service.restrict_source(db, actor, session_id, source, runtime))
    assert service.read_state(db, actor, session_id, runtime).effective_status == "blocked"


def test_parent_child_preparing(pg):
    question(pg.graph)
    delivered(pg.graph)
    db, actor, _, session_id, runtime, _ = pg.graph
    parent = command(pg.graph, "request_response", apply=False)
    entered, release = threading.Event(), threading.Event()
    outcomes = []

    def worker():
        with Session(pg.engine) as d:
            client = KernelClient(d)
            client.hook = lambda req: (
                (entered.set(), release.wait(8))
                if req.event and req.event.kind == "replace_selection"
                else None
            )
            outcomes.append(service.apply(d, actor, session_id, parent.id, runtime, client))

    thread = threading.Thread(target=worker)
    pg.handles.append(thread)
    thread.start()
    assert entered.wait(5)
    assert (
        db.scalar(
            select(func.count())
            .select_from(InterviewAgentTurn)
            .where(
                InterviewAgentTurn.session_id == session_id,
                InterviewAgentTurn.execution_status == "preparing",
            )
        )
        == 1
    )
    assert (
        db.get(InterviewAgentTurn, parent.id, populate_existing=True).execution_status == "queued"
    )
    assert (
        db.get(InterviewAgentState, session_id, populate_existing=True).active_command_id
        == parent.id
    )
    db.rollback()
    command(pg.graph, "pause", apply=False)
    release.set()
    thread.join(15)
    assert not thread.is_alive() and outcomes
    assert service.read_state(db, actor, session_id, runtime).effective_status == "paused"


@pytest.mark.parametrize("late", ["ready", "timeout"])
def test_old_generation_after_stop_cannot_poison_new(pg, late):
    db, actor, _, session_id, runtime, _ = pg.graph
    command(pg.graph, "request_response")
    old_id = db.scalar(
        select(AgentEffect.id).where(
            AgentEffect.session_id == session_id, AgentEffect.kind == "generate"
        )
    )
    db.rollback()
    entered, release = threading.Event(), threading.Event()
    outcomes, generation_calls = [], []

    def worker():
        with Session(pg.engine) as d:
            client = KernelClient(d)

            def wait_old(request):
                if request.operation == "generate":
                    generation_calls.append(request.call_id)
                    entered.set()
                    assert release.wait(12)
                    if late == "timeout":
                        raise TimeoutError("synthetic old unknown")

            client.hook = wait_old
            try:
                outcomes.append(service.dispatch(d, actor, session_id, old_id, runtime, client).id)
            except AppException as exc:
                outcomes.append(exc.code)

    thread = threading.Thread(target=worker)
    pg.handles.append(thread)
    thread.start()
    assert entered.wait(5)
    command(pg.graph, "pause")
    command(pg.graph, "resume")
    question(pg.graph)
    new = service.read_state(db, actor, session_id, runtime)
    db.rollback()
    assert new.ready_response_id
    release.set()
    thread.join(15)
    assert not thread.is_alive() and len(outcomes) == 1 and len(generation_calls) == 1
    current = service.read_state(db, actor, session_id, runtime)
    assert current == new and current.effective_status == "ready"
    old = db.get(AgentEffect, old_id, populate_existing=True)
    assert old.status == "discarded"
    assert old.dispatch_outcome == ("unknown" if late == "timeout" else "returned")


def test_unknown_first_cannot_be_cleared_by_other_connection(pg):
    db, actor, _, session_id, runtime, client = pg.graph
    command(pg.graph, "request_response")
    effect_id = db.scalar(
        select(AgentEffect.id).where(
            AgentEffect.session_id == session_id, AgentEffect.kind == "generate"
        )
    )
    db.rollback()
    entered, release = threading.Event(), threading.Event()

    def unknown_worker(d):
        client = KernelClient(d)

        def timeout(request):
            if request.operation == "generate":
                entered.set()
                raise TimeoutError("synthetic unknown first")

        client.hook = timeout
        try:
            service.dispatch(d, actor, session_id, effect_id, runtime, client)
        except AppException as exc:
            assert exc.code == "DIALOGUE_GENERATION_UNKNOWN"
        release.set()
        return "unknown"

    def after_unknown(d):
        assert entered.wait(5) and release.wait(8)
        with pytest.raises(AppException) as caught:
            service.submit(
                d,
                actor,
                session_id,
                c.CommandCreate(action="pause", expected_version=0),
                uuid.uuid4(),
                runtime,
            )
        assert caught.value.code == "DIALOGUE_STATE_UNAVAILABLE"
        return "blocked"

    results, failures = race(pg, unknown_worker, after_unknown)
    assert not failures and sorted(results) == ["blocked", "unknown"]
    current = service.read_state(db, actor, session_id, runtime)
    assert current.effective_status == "blocked"
    before = len(client.calls)
    with pytest.raises(AppException):
        command(pg.graph, "request_response")
    assert len(client.calls) == before


# Source-only until the separately authorized PostgreSQL run.
def test_callback_publication_vs_delivery(pg, monkeypatch):
    db, actor, _, session_id, runtime, _ = pg.graph
    command(pg.graph, "request_response")
    effect_id = db.scalar(
        select(AgentEffect.id).where(
            AgentEffect.session_id == session_id, AgentEffect.kind == "generate"
        )
    )
    db.rollback()
    committed, release = threading.Event(), threading.Event()
    results, failures = [], []
    original = service._commit

    def after_publish(session, who, sid, turn_id):
        result = original(session, who, sid, turn_id)
        turn = session.get(InterviewAgentTurn, turn_id)
        published = turn.event_kind == "response_ready" and turn.execution_status == "completed"
        session.rollback()
        if published and sid == session_id:
            committed.set()
            assert release.wait(15)
        return result

    monkeypatch.setattr(service, "_commit", after_publish)

    def worker():
        try:
            with Session(pg.engine) as d:
                results.append(
                    service.dispatch(d, actor, session_id, effect_id, runtime, KernelClient(d))
                )
        except Exception as exc:  # noqa: BLE001 - forward test failure without private details
            failures.append(type(exc).__name__)

    thread = threading.Thread(target=worker)
    pg.handles.append(thread)
    thread.start()
    try:
        assert committed.wait(8)
        assert db.get(AgentEffect, effect_id, populate_existing=True).status == "ready"
        db.rollback()
        delivered(pg.graph)
        assert db.get(AgentEffect, effect_id, populate_existing=True).status == "completed"
        db.rollback()
        assert command(pg.graph, "request_response").execution_status == "completed"
    finally:
        release.set()
        thread.join(20)
        if thread.is_alive():
            pg.safe = False
    assert not thread.is_alive() and not failures and len(results) == 1
    assert db.get(AgentEffect, effect_id, populate_existing=True).status == "completed"
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


@pytest.mark.parametrize("control", ["typing_started", "record_only"])
def test_pause_rpc_vs_later_safety_control(pg, control):
    db, actor, _, session_id, runtime, _ = pg.graph
    pause = command(pg.graph, "pause", apply=False)
    entered, release = threading.Event(), threading.Event()
    results, failures = [], []

    def worker():
        try:
            with Session(pg.engine) as d:
                client = KernelClient(d)

                def wait_pause(request):
                    if request.event and request.event.kind == "pause":
                        entered.set()
                        assert release.wait(15)

                client.hook = wait_pause
                results.append(service.apply(d, actor, session_id, pause.id, runtime, client))
        except Exception as exc:  # noqa: BLE001 - forward test failure without private details
            failures.append(type(exc).__name__)

    thread = threading.Thread(target=worker)
    pg.handles.append(thread)
    thread.start()
    try:
        assert entered.wait(8)
        action, extra = (
            ("set_mode", {"mode": "record_only"}) if control == "record_only" else (control, {})
        )
        later = command(pg.graph, action, apply=False, **extra)
        assert (
            db.get(InterviewAgentTurn, pause.id, populate_existing=True).execution_status
            == "queued"
        )
        db.rollback()
        result = service.apply(db, actor, session_id, later.id, runtime, pg.graph[-1])
        assert result.execution_status == "completed"
        assert service.read_state(db, actor, session_id, runtime).effective_status == "paused"
        db.rollback()
    finally:
        release.set()
        thread.join(20)
        if thread.is_alive():
            pg.safe = False
    assert not thread.is_alive() and not failures and len(results) == 1
    assert service.read_state(db, actor, session_id, runtime).effective_status == "paused"
    turn = db.get(InterviewAgentTurn, pause.id, populate_existing=True)
    assert turn.execution_status == "completed" and len(turn.transition_attempts) == 2
    assert turn.transition_attempts[0]["outcome"] == "superseded"
    assert (
        db.scalar(
            select(func.count())
            .select_from(InterviewMessage)
            .where(InterviewMessage.session_id == session_id)
        )
        == 0
    )


# Supplement P01: known, committed boundaries only. No driver disconnect,
# process kill or network fault injection; real UNKNOWN still belongs to RunGuard.
@pytest.mark.parametrize(
    "boundary",
    [
        "coordinator_queued",
        "child_preparing",
        "child_completed",
        "parent_preparing",
        "parent_committed_reply_lost",
    ],
)
def test_coordinator_recovery_boundaries(pg, monkeypatch, boundary):
    question(pg.graph)
    delivered(pg.graph)
    db, actor, _, sid, runtime, _ = pg.graph
    initial_context_revision = db.get(AgentCheckpoint, sid).context_revision
    parent = command(pg.graph, "request_response", apply=False)
    parent_id = parent.id
    db.rollback()
    calls, stopped, frozen = [], [], []
    original_transition, original_commit = service._transition, service._commit

    class KnownBoundary(RuntimeError):
        pass

    def transition(session, who, session_id, turn_id, root_id, *args, **kwargs):
        child = turn_id != root_id
        if boundary == "coordinator_queued" and child and not stopped:
            stopped.append(True)
            raise KnownBoundary()
        result = original_transition(session, who, session_id, turn_id, root_id, *args, **kwargs)
        if boundary == "child_completed" and child and not stopped:
            assert result.execution_status == "completed"
            stopped.append(True)
            raise KnownBoundary()
        return result

    def commit(session, who, session_id, turn_id):
        result = original_commit(session, who, session_id, turn_id)
        row = session.get(InterviewAgentTurn, turn_id)
        completed = turn_id == parent_id and row.execution_status == "completed"
        session.rollback()
        if boundary == "parent_committed_reply_lost" and completed and not stopped:
            stopped.append(True)
            raise KnownBoundary()
        return result

    monkeypatch.setattr(service, "_transition", transition)
    monkeypatch.setattr(service, "_commit", commit)
    with pg.guard.session(pg.engine) as first:
        client = KernelClient(first)

        def pending(request):
            if not request.event:
                return
            calls.append(request)
            is_child = request.event.kind == "replace_selection"
            if not stopped and (
                (boundary == "child_preparing" and is_child)
                or (boundary == "parent_preparing" and not is_child)
            ):
                frozen.append(request.model_dump(mode="json"))
                stopped.append(True)
                raise TimeoutError("synthetic pure RPC reply unavailable")

        client.hook = pending
        with pytest.raises((KnownBoundary, AppException)) as caught:
            service.apply(first, actor, sid, parent_id, runtime, client)
        if isinstance(caught.value, AppException):
            assert caught.value.code == "DIALOGUE_TRANSITION_PENDING"
    assert stopped == [True]
    monkeypatch.setattr(service, "_transition", original_transition)
    monkeypatch.setattr(service, "_commit", original_commit)
    with pg.guard.session(pg.engine) as recovered:
        root = recovered.get(InterviewAgentTurn, parent_id)
        children = list(
            recovered.scalars(
                select(InterviewAgentTurn).where(InterviewAgentTurn.parent_turn_id == parent_id)
            )
        )
        assert len(children) == 1
        child_id = children[0].id
        expected = {
            "coordinator_queued": ("queued", "queued"),
            "child_preparing": ("queued", "preparing"),
            "child_completed": ("queued", "completed"),
            "parent_preparing": ("preparing", "completed"),
            "parent_committed_reply_lost": ("completed", "completed"),
        }
        assert (root.execution_status, children[0].execution_status) == expected[boundary]
        state = recovered.get(InterviewAgentState, sid)
        assert state.active_command_id == (
            None if root.execution_status == "completed" else parent_id
        )
        assert sum(t.execution_status == "preparing" for t in [root, *children]) <= 1
        recovered.rollback()
        client = KernelClient(recovered)
        result = service.apply(recovered, actor, sid, parent_id, runtime, client)
        assert result.execution_status == "completed" and result.id == parent_id
        if frozen:
            assert client.calls[0].model_dump(mode="json") == frozen[0]
        child = recovered.get(InterviewAgentTurn, child_id, populate_existing=True)
        assert child.execution_status == "completed" and len(child.transition_attempts) == 1
        assert (
            recovered.get(AgentCheckpoint, sid, populate_existing=True).context_revision
            == initial_context_revision + 1
        )
        assert (
            recovered.get(InterviewAgentState, sid, populate_existing=True).active_command_id
            is None
        )
        assert (
            recovered.scalar(
                select(func.count())
                .select_from(InterviewAgentTurn)
                .where(InterviewAgentTurn.parent_turn_id == parent_id)
            )
            == 1
        )
        assert (
            recovered.scalar(
                select(func.count())
                .select_from(InterviewMessage)
                .where(InterviewMessage.session_id == sid)
            )
            == 1
        )
        effects = list(
            recovered.scalars(
                select(AgentEffect).where(
                    AgentEffect.session_id == sid, AgentEffect.kind == "generate"
                )
            )
        )
        assert len(effects) == 2 and sum(e.status == "reserved" for e in effects) == 1
        assert all(r.operation != "generate" for r in [*calls, *client.calls])


@pytest.mark.parametrize("boundary", ["preempted_preparing", "committed_reply_lost"])
def test_saved_source_recovery(pg, monkeypatch, boundary):
    db, actor, _, sid, runtime, _ = pg.graph
    source = put_text(pg.graph, apply=False)
    source_id, message_id = source.id, source.message_id
    human_turn_id = db.get(InterviewAgentTurn, source_id).command_payload["human_turn_id"]
    db.rollback()
    frozen, triggered = [], []
    original_commit = service._commit

    def after_commit(session, who, session_id, turn_id):
        value = original_commit(session, who, session_id, turn_id)
        row = session.get(InterviewAgentTurn, turn_id)
        complete = turn_id == source_id and row.execution_status == "completed"
        session.rollback()
        if complete and boundary == "committed_reply_lost" and not triggered:
            triggered.append(True)
            raise RuntimeError("synthetic reply lost after known commit")
        return value

    monkeypatch.setattr(service, "_commit", after_commit)
    with pg.guard.session(pg.engine) as first:
        client = KernelClient(first)
        if boundary == "preempted_preparing":

            def pending(request):
                if request.event and request.event.kind == "user_message_committed":
                    raise TimeoutError("synthetic pure transition pending")

            client.hook = pending
        with pytest.raises((AppException, RuntimeError)) as caught:
            service.apply(first, actor, sid, source_id, runtime, client)
        if boundary == "preempted_preparing":
            assert isinstance(caught.value, AppException)
            assert caught.value.code == "DIALOGUE_TRANSITION_PENDING"
        frozen = copy.deepcopy(first.get(InterviewAgentTurn, source_id).transition_attempts)
        assert len(frozen) == 1
    monkeypatch.setattr(service, "_commit", original_commit)
    if boundary == "preempted_preparing":
        command(pg.graph, "pause", apply=False)
    with pg.guard.session(pg.engine) as recovered:
        row = recovered.get(InterviewAgentTurn, source_id)
        before = copy.deepcopy(row.transition_attempts)
        assert row.command_payload["message_id"] == str(message_id)
        assert row.command_payload["human_turn_id"] == human_turn_id
        assert before[0]["event_id"] == frozen[0]["event_id"]
        if boundary == "preempted_preparing":
            assert before[0]["outcome"] == "superseded"
        else:
            assert (
                service.read_command(recovered, actor, sid, source_id).execution_status
                == "completed"
            )
        recovered.rollback()
        client = KernelClient(recovered)
        result = service.apply(recovered, actor, sid, source_id, runtime, client)
        assert result.execution_status == "completed" and result.message_id == message_id
        row = recovered.get(InterviewAgentTurn, source_id, populate_existing=True)
        assert row.transition_attempts[:1] == before
        assert len(row.transition_attempts) == (2 if boundary == "preempted_preparing" else 1)
        if boundary == "preempted_preparing":
            assert row.transition_attempts[-1]["event_id"] == str(
                uuid.uuid5(row.event_id, "transition:2")
            )
        assert (
            recovered.scalar(
                select(func.count())
                .select_from(InterviewMessage)
                .where(InterviewMessage.session_id == sid)
            )
            == 1
        )
        assert all(r.operation != "generate" for r in client.calls)
        if boundary == "committed_reply_lost":
            assert not client.calls and triggered == [True]


@pytest.mark.parametrize(
    "interference", ["new_coordinator", "new_source", "end_preempts_parent_child"]
)
def test_stale_coordinator_reply(pg, interference):
    question(pg.graph)
    delivered(pg.graph)
    db, actor, _, sid, runtime, _ = pg.graph
    parent = command(pg.graph, "request_response", apply=False)
    parent_id = parent.id
    entered, release = threading.Event(), threading.Event()
    results, failures, calls = [], [], []

    def worker():
        try:
            session = Session(pg.engine)
            pg.guard.resources.append(session)
            try:
                client = KernelClient(session)

                def wait_child(request):
                    calls.append(request)
                    if request.event and request.event.kind == "replace_selection":
                        entered.set()
                        assert release.wait(8)

                client.hook = wait_child
                results.append(service.apply(session, actor, sid, parent_id, runtime, client))
            finally:
                # Keep the registered Session untouched if its outcome became UNKNOWN.
                pg.guard.check()
                session.close()
        except Exception as exc:  # noqa: BLE001 - no SQL or source-bearing exception text
            failures.append(type(exc).__name__)

    db.rollback()
    thread = threading.Thread(target=worker)
    pg.handles.append(thread)
    thread.start()
    newer_id, new_source_id = None, None
    try:
        assert entered.wait(5)
        child = db.scalar(
            select(InterviewAgentTurn).where(InterviewAgentTurn.parent_turn_id == parent_id)
        )
        child_id = child.id
        assert child.execution_status == "preparing"
        assert (
            db.get(InterviewAgentTurn, parent_id, populate_existing=True).execution_status
            == "queued"
        )
        db.rollback()
        if interference == "end_preempts_parent_child":
            command(pg.graph, "end")
            state = service.read_state(db, actor, sid, runtime)
            assert state.session_status == "completed" and state.effective_status == "ended"
        elif interference == "new_source":
            saved = put_text(pg.graph, apply=False)
            new_source_id = saved.id
        else:
            command(pg.graph, "pause")
            command(pg.graph, "resume")
            newer = command(pg.graph, "request_response", apply=False)
            newer_id = newer.id
            session = Session(pg.engine)
            pg.guard.resources.append(session)
            try:
                client = KernelClient(session)

                def leave_preparing(request):
                    if request.event and request.event.kind == "replace_selection":
                        raise TimeoutError("synthetic newer coordinator pending")

                client.hook = leave_preparing
                with pytest.raises(AppException) as caught:
                    service.apply(session, actor, sid, newer_id, runtime, client)
                assert caught.value.code == "DIALOGUE_TRANSITION_PENDING"
            finally:
                pg.guard.check()
                session.close()
            assert (
                db.get(InterviewAgentState, sid, populate_existing=True).active_command_id
                == newer_id
            )
        db.rollback()
    finally:
        release.set()
        thread.join(15)
        if thread.is_alive():
            pg.safe = False
            pg.guard.retain("SupplementWorkerExitUnknown")
    assert not thread.is_alive() and not failures and len(results) == 1
    assert results[0].id == parent_id and results[0].execution_status == "discarded"
    state = db.get(InterviewAgentState, sid, populate_existing=True)
    assert state.active_command_id == newer_id
    assert (
        db.get(InterviewAgentTurn, child_id, populate_existing=True).execution_status == "discarded"
    )
    assert (
        db.get(InterviewAgentTurn, parent_id, populate_existing=True).execution_status
        == "discarded"
    )
    assert all(r.operation != "generate" for r in calls)
    if interference == "end_preempts_parent_child":
        assert state.status == "ended" and state.checkpoint_status == "unavailable"
        assert db.get(AgentCheckpoint, sid, populate_existing=True).sensitive_json is None
        assert (
            db.scalar(
                select(func.count())
                .select_from(AgentEffect)
                .where(
                    AgentEffect.session_id == sid,
                    AgentEffect.status.in_(["reserved", "claimed", "ready", "published"]),
                )
            )
            == 0
        )
    if new_source_id:
        db.rollback()
        applied = service.apply(db, actor, sid, new_source_id, runtime, pg.graph[-1])
        assert applied.execution_status == "completed"
        assert service.apply(db, actor, sid, new_source_id, runtime, pg.graph[-1]) == applied
        assert (
            db.scalar(
                select(func.count())
                .select_from(InterviewMessage)
                .where(InterviewMessage.session_id == sid, InterviewMessage.role == "user")
            )
            == 1
        )
