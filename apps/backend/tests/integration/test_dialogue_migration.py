"""Manager Owner only, exact disposable allocation. No Runner DDL authority."""

import importlib.util
import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from tests.integration.test_dialogue import RunGuard

pytestmark = pytest.mark.integration
HEAD = "c296a4e8d102"
PARENT = "b196f0d47a21"
BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture
def manager(request, monkeypatch):
    run = uuid.UUID(os.environ["DIALOGUE_ALLOCATION_RUN_ID"])
    raw = os.environ["TEST_DATABASE_URL"]
    url = make_url(raw)
    if (
        url.database != "ai_memoir_dialogue_ci_test_" + run.hex
        or url.database != os.environ["DIALOGUE_ALLOCATED_DATABASE"]
        or url.username != "d_ci_owner_" + run.hex
        or url.host != "127.0.0.1"
        or not url.port
        or url.get_backend_name() != "postgresql"
    ):
        raise pytest.UsageError("Manager migration allocation mismatch")
    engine = create_engine(
        raw,
        pool_reset_on_return=None,
        connect_args={
            "connect_timeout": 5,
            "options": "-c statement_timeout=8000 -c lock_timeout=4000",
        },
    )
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    guard = RunGuard(request, raw)
    guard.resources.append(engine)
    guard.install()
    config._dialogue_guard = guard
    # Alembic creates its own engines; RunGuard's target-scoped Engine events
    # cover their SQL/commit/rollback as well as this fixture's connections.
    for name in ("upgrade", "downgrade", "check"):
        original = getattr(command, name)

        def checked(*args, _operation=original, **kwargs):
            guard.check()
            return _operation(*args, **kwargs)

        monkeypatch.setattr(command, name, checked)
    with engine.connect() as connection:
        assert int(connection.scalar(text("SHOW server_version_num"))) == 160015
        assert connection.scalar(text("SELECT current_user")) == url.username
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
    try:
        yield engine, config
    finally:
        # Only confirmed, quiescent work may restore schema. UNKNOWN must leave
        # the original resources untouched for the trusted Manager.
        guard.finish()
        command.upgrade(config, HEAD)
        engine.dispose()
        guard.uninstall()


def migration_source():
    path = BACKEND / "alembic/versions/c296a4e8d102_session_text_dialogue.py"
    spec = importlib.util.spec_from_file_location("dialogue_migration_snapshot", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_legacy_upgrade(manager):
    engine, config = manager
    command.downgrade(config, PARENT)
    # Reflect the actual legacy schema. No current ORM columns are inserted here.
    from sqlalchemy import MetaData, Table

    metadata = MetaData()
    tables = {
        name: Table(name, metadata, autoload_with=engine)
        for name in (
            "users",
            "families",
            "family_members",
            "interviews",
            "interview_sessions",
            "interview_messages",
            "interview_agent_states",
            "interview_agent_turns",
        )
    }
    ids = {name: uuid.uuid4() for name in tables}
    with engine.begin() as connection:
        connection.execute(
            tables["users"]
            .insert()
            .values(
                id=ids["users"],
                email=f"legacy-{uuid.uuid4().hex}@example.com",
                password_hash="synthetic",
                is_active=True,
            )
        )
        connection.execute(
            tables["families"]
            .insert()
            .values(id=ids["families"], owner_id=ids["users"], name="Synthetic legacy")
        )
        connection.execute(
            tables["family_members"]
            .insert()
            .values(id=ids["family_members"], family_id=ids["families"], name="Synthetic legacy")
        )
        connection.execute(
            tables["interviews"]
            .insert()
            .values(
                id=ids["interviews"],
                family_member_id=ids["family_members"],
                title="Synthetic legacy",
                status="draft",
                type="other",
            )
        )
        connection.execute(
            tables["interview_sessions"]
            .insert()
            .values(id=ids["interview_sessions"], interview_id=ids["interviews"], status="active")
        )
        connection.execute(
            tables["interview_messages"]
            .insert()
            .values(
                id=ids["interview_messages"],
                session_id=ids["interview_sessions"],
                role="user",
                source="text",
                sequence=1,
                content="Synthetic legacy source",
            )
        )
        connection.execute(
            tables["interview_agent_states"]
            .insert()
            .values(
                session_id=ids["interview_sessions"],
                contract_version="interview-agent.v2",
                status="idle",
                version=0,
                generation_epoch=0,
                policy_version="synthetic-legacy.v1",
            )
        )
        legacy_session = uuid.uuid4()
        connection.execute(
            tables["interview_sessions"]
            .insert()
            .values(id=legacy_session, interview_id=ids["interviews"], status="active")
        )
        connection.execute(
            tables["interview_agent_states"]
            .insert()
            .values(
                session_id=legacy_session,
                contract_version="interview-agent.v1",
                status="ended",
                version=3,
                generation_epoch=0,
                policy_version="synthetic-legacy.v1",
            )
        )
        for contract, session in (
            ("interview-agent.v1", legacy_session),
            ("interview-agent.v2", ids["interview_sessions"]),
        ):
            turn = {
                "id": uuid.uuid4(),
                "session_id": session,
                "actor_user_id": ids["users"],
                "idempotency_key": uuid.uuid4(),
                "contract_version": contract,
                "action": "start",
                "request_fingerprint": b"s" * 32,
                "execution_status": "completed",
                "result_kind": "control",
                "result_state_contract_version": contract,
                "resulting_version": 1,
                "resulting_status": "awaiting_answer" if contract.endswith("v1") else "idle",
            }
            if contract.endswith("v2"):
                from datetime import UTC, datetime

                turn.update(
                    reserved_version=0,
                    reserved_epoch=0,
                    context_present=False,
                    asked_question_message_ids=[],
                    finished_at=datetime.now(UTC),
                )
            connection.execute(tables["interview_agent_turns"].insert().values(**turn))
        before = (
            connection.execute(text("SELECT * FROM interview_agent_states ORDER BY session_id"))
            .mappings()
            .all()
        )
        turns_before = (
            connection.execute(text("SELECT * FROM interview_agent_turns ORDER BY id"))
            .mappings()
            .all()
        )
        source_before = (
            connection.execute(text("SELECT * FROM interview_messages")).mappings().all()
        )
    try:
        command.upgrade(config, HEAD)
        with engine.connect() as connection:
            after = (
                connection.execute(text("SELECT * FROM interview_agent_states ORDER BY session_id"))
                .mappings()
                .all()
            )
            assert [{key: row[key] for key in before[0]} for row in after] == before
            turns_after = (
                connection.execute(text("SELECT * FROM interview_agent_turns ORDER BY id"))
                .mappings()
                .all()
            )
            assert [
                {key: row[key] for key in turns_before[0]} for row in turns_after
            ] == turns_before
            assert all(
                row["integration_profile"] is None and row["transition_attempts"] is None
                for row in turns_after
            )
            assert all(
                row["integration_profile"] is None and row["persistence_version"] is None
                for row in after
            )
            assert (
                connection.execute(text("SELECT * FROM interview_messages")).mappings().all()
                == source_before
            )
    finally:
        config._dialogue_guard.finish()
        with engine.begin() as connection:
            connection.execute(
                tables["families"].delete().where(tables["families"].c.id == ids["families"])
            )
            connection.execute(tables["users"].delete().where(tables["users"].c.id == ids["users"]))


def test_marker_downgrade_refusal(manager):
    engine, config = manager
    module = migration_source()
    # Every field marker is covered, including predicates dominated by its parent
    # FK/table guard. Do not manufacture impossible orphan rows to hit each OR.
    for name in ("contexts", "checkpoints", "sources", "effects", "dependencies"):
        assert f"EXISTS (SELECT 1 FROM interview_agent_{name})" in module.GUARD_SQL
    inspector = inspect(engine)
    for table, legacy_count in (("interview_agent_states", 10), ("interview_agent_turns", 29)):
        columns = inspector.get_columns(table)
        assert len(columns) > legacy_count
        for column in columns[legacy_count:]:
            assert column["name"] + " IS NOT NULL" in module.GUARD_SQL

    # A real v3 marker with valid parents must refuse before any DROP/ALTER.

    from app.models.family import Family
    from app.models.family_member import FamilyMember
    from app.models.interview import Interview
    from app.models.interview_session import InterviewSession
    from app.models.user import User
    from app.schemas import dialogue as c
    from app.services.dialogue_policy import Integrity, Runtime
    from tests.test_dialogue import Allocation, KernelClient
    from tests.test_dialogue import command as submit_command

    with config._dialogue_guard.session(engine) as db:
        owner = User(email=f"guard-{uuid.uuid4().hex}@example.com", password_hash="synthetic")
        db.add(owner)
        db.flush()
        family = Family(owner_id=owner.id, name="Synthetic guard")
        db.add(family)
        db.flush()
        member = FamilyMember(family_id=family.id, name="Synthetic guard")
        db.add(member)
        db.flush()
        interview = Interview(family_member_id=member.id, title="Synthetic guard")
        db.add(interview)
        db.flush()
        session = InterviewSession(interview_id=interview.id, status="active")
        db.add(session)
        db.commit()
        actor, session_id, family_id = owner.id, session.id, family.id
        runtime = Runtime(
            Allocation(actor, session_id),
            c.Policy(
                version="synthetic-guard.v1",
                complete_pause_ms=5,
                uncertain_pause_ms=10,
                max_events=200,
                max_sources=50,
                max_context_chars=100000,
                max_history_items=10,
                max_summary_entries=50,
                mode="light",
            ),
            Integrity({"synthetic": b"s" * 32}, "synthetic"),
            1000,
        )
        graph = (db, actor, uuid.uuid4(), session_id, runtime, KernelClient(db))
        submit_command(graph, "start")
        db.rollback()
        try:
            with pytest.raises(RuntimeError, match="prevent downgrade"):
                command.downgrade(config, PARENT)
            with engine.connect() as connection:
                assert connection.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
                assert inspect(connection).has_table("interview_agent_contexts")
        finally:
            config._dialogue_guard.finish()
            from sqlalchemy import delete

            db.execute(delete(Family).where(Family.id == family_id))
            db.execute(delete(User).where(User.id == actor))
            db.commit()


def test_legacy_downgrade_reupgrade(manager):
    engine, config = manager
    command.downgrade(config, PARENT)
    inspector = inspect(engine)
    assert "interview_agent_effects" not in inspector.get_table_names()
    assert len(inspector.get_columns("interview_agent_states")) == 10
    assert len(inspector.get_columns("interview_agent_turns")) == 29
    checks = {row["name"] for row in inspector.get_check_constraints("interview_agent_turns")}
    assert "ck_agent_turn_lifecycle" in checks
    command.upgrade(config, HEAD)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == HEAD


def test_schema_matches_metadata(manager):
    _, config = manager
    command.check(config)
