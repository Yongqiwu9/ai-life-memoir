"""Subprocess-only C3.1 DDL probe; never imported by test collection.

PostgreSQL writes are confined to a generated schema in the guarded test DB.
Raw exceptions, URLs and stderr are never forwarded by the parent tests.
"""

import io
import json
import os
import sys
import uuid
from contextlib import contextmanager, redirect_stdout

from sqlalchemy import JSON, create_engine, delete, event, func, inspect, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session


@contextmanager
def isolated_session(engine):
    with engine.connect() as connection:
        transaction = connection.begin()
        db = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield db
        finally:
            db.close()
            transaction.rollback()


def expect_integrity(db, action):
    try:
        with db.begin_nested():
            action()
            db.flush()
    except IntegrityError:
        return
    raise AssertionError("Expected structural integrity rejection")


def run_cases(engine, artifact):
    from app.models.family import Family
    from app.models.family_member import FamilyMember
    from app.models.identity_foundation import PrivacyPolicyVersion
    from app.models.interview import Interview
    from app.models.interview_session import InterviewSession
    from app.models.user import User

    table = artifact.__table__
    expected = {
        "id",
        "family_id",
        "interview_id",
        "session_id",
        "family_scope_id",
        "interview_scope_id",
        "kind",
        "entity_id",
        "operator_user_id",
        "state",
        "generation",
        "content_digest",
        "locator",
        "policy_version_id",
        "created_at",
        "updated_at",
    }
    assert set(table.columns.keys()) == expected
    assert table.c.state.default is None and table.c.state.server_default is None
    assert table.c.generation.default is None and table.c.generation.server_default is None
    assert table.c.entity_id.nullable and table.c.interview_scope_id.nullable
    assert not table.c.family_scope_id.nullable
    assert table.c.created_at.type.timezone and table.c.updated_at.type.timezone
    for name in (
        "id",
        "family_id",
        "interview_id",
        "session_id",
        "family_scope_id",
        "interview_scope_id",
        "entity_id",
        "operator_user_id",
        "policy_version_id",
    ):
        assert table.c[name].type.python_type is uuid.UUID
    assert table.c.kind.type.length == 32 and table.c.state.type.length == 32
    assert table.c.generation.type.__class__.__name__ == "BigInteger"
    assert table.c.content_digest.type.python_type is bytes
    assert table.c.created_at.server_default is not None
    assert table.c.updated_at.server_default is not None and table.c.updated_at.onupdate is not None
    inspected = inspect(engine)
    keys = {tuple(item["column_names"]) for item in inspected.get_unique_constraints(table.name)}
    assert {("kind", "entity_id"), ("id", "family_scope_id"), ("id", "interview_scope_id")} <= keys
    indexes = {tuple(item["column_names"]) for item in inspected.get_indexes(table.name)}
    assert {
        ("family_scope_id", "state"),
        ("interview_scope_id", "state"),
        ("family_scope_id", "generation"),
    } <= indexes
    actions = {
        tuple(item["constrained_columns"]): item["options"].get("ondelete")
        for item in inspected.get_foreign_keys(table.name)
    }
    assert actions == {
        ("family_id",): "SET NULL",
        ("interview_id",): "SET NULL",
        ("session_id",): "SET NULL",
        ("operator_user_id",): "RESTRICT",
        ("policy_version_id",): "RESTRICT",
    }
    if engine.dialect.name == "postgresql":
        types = {
            item["name"]: item["type"].__class__.__name__
            for item in inspected.get_columns(table.name)
        }
        assert types["locator"] == "JSONB" and types["content_digest"] == "BYTEA"
        assert types["id"] == "UUID" and types["generation"] == "BIGINT"
    result = {"definition": "PASS"}

    def new(**changes):
        values = {
            "family_scope_id": uuid.uuid4(),
            "interview_scope_id": uuid.uuid4(),
            "kind": "interview_message",
            "entity_id": uuid.uuid4(),
            "state": "quarantined",
            "generation": 1,
            "locator": None,
        }
        values.update(changes)
        return artifact(**values)

    with isolated_session(engine) as db:
        item = new()
        db.add(item)
        db.flush()
        assert isinstance(item.id, uuid.UUID)
        assert item.created_at is not None and item.updated_at is not None
        assert item.content_digest is None
        if engine.dialect.name == "postgresql":
            assert item.created_at.tzinfo is not None
        for kind in ("audio_recording", "transcript", "transcript_segment", "interview_message"):
            db.add(new(kind=kind))
        for state in ("legacy_unknown", "quarantined", "available", "deletion_pending", "erased"):
            # Structural domain only: later states are not a C3 creation workflow.
            db.add(new(state=state))
        db.flush()
        result["creation"] = "PASS"
        for change in (
            {"kind": None},
            {"kind": "memory"},
            {"state": "verified"},
            {"generation": 0},
            {"generation": -1},
            {"generation": None},
            {"state": None},
            {"family_scope_id": None},
            {"entity_id": None},
            {"interview_scope_id": None},
        ):
            expect_integrity(db, lambda change=change: db.add(new(**change)))
        result["checks"] = "PASS"
        assert db.scalar(select(table.c.locator.is_(None)).where(table.c.id == item.id)) is True
        for locator in ({}, {"text": "excerpt"}, "payload", {"prompt": "secret"}, JSON.NULL):
            expect_integrity(db, lambda locator=locator: db.add(new(locator=locator)))
        result["locator"] = "PASS"
        expect_integrity(db, lambda: db.add(new(kind=item.kind, entity_id=item.entity_id)))
        expect_integrity(db, lambda: db.add(new(id=item.id, family_scope_id=item.family_scope_id)))
        # PostgreSQL normally permits repeated NULL unique components; the C3
        # non-NULL CHECK closes that gap for both entity and interview scope.
        expect_integrity(db, lambda: db.add(new(entity_id=None)))
        result["unique"] = "PASS"

    with isolated_session(engine) as db:
        owner = User(email=f"owner-{uuid.uuid4().hex}@example.com", password_hash="test-only")
        operator = User(email=f"operator-{uuid.uuid4().hex}@example.com", password_hash="test-only")
        policy = PrivacyPolicyVersion(
            version=uuid.uuid4().hex,
            state="draft",
            parameters={},
            notices={},
            capabilities={},
            digest=uuid.uuid4().bytes + uuid.uuid4().bytes,
        )
        family = Family(owner=owner, name="Probe")
        member = FamilyMember(family=family, name="Subject")
        interview = Interview(member=member, title="Probe")
        session = InterviewSession(interview=interview)
        db.add_all([owner, operator, policy, family, member, interview, session])
        db.flush()
        item = new(
            # Test-only terminal-state fixture for physical FK mechanics.
            # This is not a C3 creation/transition or deletion authorization.
            state="erased",
            family_id=family.id,
            interview_id=interview.id,
            session_id=session.id,
            family_scope_id=family.id,
            interview_scope_id=interview.id,
            operator_user_id=operator.id,
            policy_version_id=policy.id,
        )
        db.add(item)
        db.flush()
        for field in (
            "family_id",
            "interview_id",
            "session_id",
            "operator_user_id",
            "policy_version_id",
        ):
            expect_integrity(db, lambda field=field: db.add(new(**{field: uuid.uuid4()})))
        expect_integrity(db, lambda: db.execute(delete(User).where(User.id == operator.id)))
        expect_integrity(
            db,
            lambda: db.execute(
                delete(PrivacyPolicyVersion).where(PrivacyPolicyVersion.id == policy.id)
            ),
        )
        scope = (item.family_scope_id, item.interview_scope_id)
        # Exercise each SET NULL action independently, avoiding multiple
        # cascading paths in a single statement on PostgreSQL 16.15. Ordinary
        # live-state content deletion must be rejected by later C3 guards;
        # this structural probe neither implements nor bypasses those guards.
        db.execute(delete(InterviewSession).where(InterviewSession.id == session.id))
        db.refresh(item)
        assert item.session_id is None
        assert item.interview_id == interview.id and item.family_id == family.id
        assert (item.family_scope_id, item.interview_scope_id) == scope
        db.execute(delete(Interview).where(Interview.id == interview.id))
        db.refresh(item)
        assert item.interview_id is None and item.family_id == family.id
        assert (item.family_scope_id, item.interview_scope_id) == scope
        db.execute(delete(Family).where(Family.id == family.id))
        db.flush()
        db.refresh(item)
        assert item.family_id is None and item.interview_id is None and item.session_id is None
        assert (item.family_scope_id, item.interview_scope_id) == scope
        result["fk"] = "PASS"
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(artifact)) == 0
        result["rollback"] = "PASS"
    return result


def probe(mode):
    from app.database import models_import  # noqa: F401
    from app.database.base import Base

    assert "source_artifacts" not in Base.metadata.tables
    if mode == "sqlite":
        engine = create_engine("sqlite://", hide_parameters=True)

        @event.listens_for(engine, "connect")
        def enable_fk(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

        from app.models.source_artifact import SourceArtifact

        try:
            Base.metadata.create_all(engine)
            return run_cases(engine, SourceArtifact)
        finally:
            engine.dispose()

    from alembic import command
    from alembic.config import Config
    from sqlalchemy.engine import make_url

    from test_support.database import resolve_test_database_url

    url = make_url(resolve_test_database_url())
    admin = create_engine(url, hide_parameters=True)
    schema = "c3_1_probe_" + uuid.uuid4().hex
    created = False
    engine = None
    try:
        with admin.connect() as connection:
            assert (
                "test" in connection.execute(text("SELECT current_database()")).scalar_one().lower()
            )
            version = int(connection.execute(text("SHOW server_version_num")).scalar_one())
            assert version == 160015, "PostgreSQL 16.15 required"
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            created = True
        isolated = url.set(query={**url.query, "options": f"-csearch_path={schema}"})
        os.environ["TEST_DATABASE_URL"] = isolated.render_as_string(hide_password=False)
        os.environ["TEST_MIGRATION_MODE"] = "1"
        # Config captures its stdout at construction; redirect_stdout alone
        # does not capture command.check's Config.print_stdout output.
        config = Config("alembic.ini", stdout=io.StringIO())
        with redirect_stdout(io.StringIO()):
            command.upgrade(config, "head")
            command.check(config)
        from app.models.source_artifact import SourceArtifact

        engine = create_engine(isolated, hide_parameters=True)
        SourceArtifact.__table__.create(engine)
        result = run_cases(engine, SourceArtifact)
        SourceArtifact.__table__.drop(engine)
        # Child-only cleanup restores the baseline metadata for an independent
        # post-probe Alembic check. Parent metadata was never changed.
        Base.metadata.remove(SourceArtifact.__table__)
        with redirect_stdout(io.StringIO()):
            command.check(config)
        result["baseline"] = "PASS"
        return result
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


if __name__ == "__main__":
    try:
        print(json.dumps(probe(sys.argv[1])))
    except (SQLAlchemyError, ValueError, AssertionError, RuntimeError, OSError) as error:
        # Never output a DB exception representation or URL with credentials.
        print(json.dumps({"error_category": type(error).__name__}))
        sys.exit(1)
