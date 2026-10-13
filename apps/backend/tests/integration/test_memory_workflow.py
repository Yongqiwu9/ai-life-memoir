"""SOURCE ONLY: future Memory workflow PostgreSQL 16.15 acceptance.

Run only after a separately authorized trusted Manager allocates and migrates a
unique disposable database, supplies the exact allocation metadata, and arranges
cleanup after all Runner processes/threads exit. These tests never provision,
migrate, drop, or connect to an arbitrary second database. Environment metadata
is an additional guard, not a replacement for that task-specific authorization.

Separate migration acceptance remains required: Manager prepares a fresh 16.15
database at b196f0d47a21 and a legacy fixture upgraded from a196e4c72b08; verify
unchanged legacy IDs/body bytes, zero metadata counters and NULL current/proof
without fabricated identity/Consent/approval, then Alembic current/check. In a
separately authorized fixture, verify downgrade refuses every B business row or
reference and accepts only empty/pure-legacy data. This module checks the already
prepared schema and runtime constraints, not execution of those migration steps.
"""

import os
import threading
import time
import uuid
from datetime import UTC, datetime
from queue import Queue
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, event, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.models.collaboration import CommandIdempotencyRecord
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.interview import Interview
from app.models.interview_message import InterviewMessage
from app.models.interview_session import InterviewSession
from app.models.memoir import Memoir, MemoirSection
from app.models.memory import Memory
from app.models.memory_workflow import (
    PROTECTED_DELETE_FK_MANIFEST,
    ContentRevision,
    ExtractionBatch,
    MemoryCandidate,
    RevisionProposal,
)
from app.models.user import User
from app.schemas.memoir import MemoirCreate
from app.schemas.memory_workflow import (
    ManualCandidateCreate,
    ProposalApprove,
    ProposalSubmit,
    RevisionCreate,
)
from app.services import memoir as memoir_service
from app.services import memory_review
from app.services.memory_integrity import MemoryIntegrity, SyntheticKeyProvider
from app.services.memory_policy import PURPOSES, DecisionStamp, SyntheticMemoryPolicy

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session", autouse=True)
def memory_b_allocation():
    """Reject before the inherited postgres_engine can open a connection."""
    run_text = os.environ.get("MEMORY_B_ALLOCATION_RUN_ID")
    database = os.environ.get("MEMORY_B_ALLOCATED_DATABASE")
    runner = os.environ.get("MEMORY_B_RUNNER_ROLE")
    raw_url = os.environ.get("TEST_DATABASE_URL")
    if not all((run_text, database, runner, raw_url)):
        raise pytest.UsageError(
            "B PostgreSQL tests require a separately verified Manager allocation"
        )
    try:
        run_id = uuid.UUID(run_text)
        url = make_url(raw_url)
    except (ValueError, TypeError):
        raise pytest.UsageError("Invalid B allocation metadata") from None
    if (
        url.get_backend_name() != "postgresql"
        or url.database != database
        or url.username != runner
        or "test" not in database.lower()
        or not database.endswith(run_id.hex)
        or database == "ai_life_memoir_c3_test"
        or runner in {"postgres", "c3_test_user"}
    ):
        raise pytest.UsageError("B allocation endpoint does not match the verified disposable run")
    return SimpleNamespace(run_id=run_id, database=database, runner=runner)


@pytest.fixture()
def db_session(memory_b_allocation, postgres_engine):
    """Existing allocated engine only, with one rollback-isolated case transaction."""
    connection = postgres_engine.connect()
    transaction = connection.begin()
    session = None
    try:
        version = connection.execute(text("SELECT version()")).scalar_one()
        number = connection.execute(text("SHOW server_version_num")).scalar_one()
        if int(number) != 160015 or not version.startswith("PostgreSQL 16.15"):
            raise pytest.UsageError("B authoritative integration database must be PostgreSQL 16.15")
        identity = connection.execute(text("SELECT current_database(), current_user")).one()
        if identity != (memory_b_allocation.database, memory_b_allocation.runner):
            raise pytest.UsageError("B database/Runner identity differs from the assigned run")
        privileges = connection.execute(
            text(
                "SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls "
                "FROM pg_roles WHERE rolname = current_user"
            )
        ).one()
        if any(privileges):
            raise pytest.UsageError("B Runner must not have administrative database privileges")
        schema = inspect(connection)
        required = {
            "memory_extraction_batches",
            "memory_candidates",
            "memory_content_revisions",
            "revision_proposals",
        }
        if not required.issubset(schema.get_table_names()):
            raise pytest.UsageError(
                "Manager must migrate the allocated B test database before Runner tests"
            )
        head = connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
        if head != ["b196f0d47a21"]:
            raise pytest.UsageError(
                "Allocated test schema is not at the exact B migration revision"
            )
        session = Session(
            bind=connection,
            autoflush=False,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        yield session
    finally:
        if session is not None:
            session.close()
        transaction.rollback()
        connection.close()


def _graph(db):
    owner = User(email=f"b-pg-{uuid.uuid4().hex}@example.com", password_hash="synthetic")
    db.add(owner)
    db.flush()
    family = Family(owner_id=owner.id, name="Synthetic PG case")
    db.add(family)
    db.flush()
    member = FamilyMember(family_id=family.id, name="Synthetic subject")
    db.add(member)
    db.flush()
    interview = Interview(family_member_id=member.id, title="Synthetic", type="life_story")
    db.add(interview)
    db.flush()
    session = InterviewSession(interview_id=interview.id, status="completed")
    db.add(session)
    db.flush()
    message = InterviewMessage(
        session_id=session.id, role="user", source="text", content="Synthetic source", sequence=1
    )
    db.add(message)
    db.flush()
    return SimpleNamespace(
        owner=owner,
        family=family,
        member=member,
        interview=interview,
        session=session,
        message=message,
    )


def _capabilities(graph):
    stamp = DecisionStamp(
        operation="synthetic_fixture",
        actor_user_id=graph.owner.id,
        family_scope_id=graph.family.id,
        family_member_id=graph.member.id,
        source_scope_id=graph.message.id,
        source_generation=1,
        required_purposes=tuple(sorted(PURPOSES)),
        purpose_generations={purpose: 1 for purpose in PURPOSES},
        allow=True,
        body_available=True,
        restore_verified=True,
    )
    return (
        SyntheticMemoryPolicy({graph.message.id: stamp}),
        MemoryIntegrity(SyntheticKeyProvider({"synthetic-pg": b"p" * 32}, "synthetic-pg")),
    )


def _payload():
    return {
        "title": "Synthetic PG fragment",
        "content": "Synthetic source",
        "time_text": None,
        "place": None,
        "emotion": None,
        "uncertainties": [],
    }


def _batch(graph, state="pending"):
    terminal = state != "pending"
    return ExtractionBatch(
        requested_by_user_id=graph.owner.id,
        session_id=graph.session.id,
        family_member_id=graph.member.id,
        family_scope_id=graph.family.id,
        source_message_id=graph.message.id,
        source_scope_id=graph.message.id,
        contract_version="memory-extraction.v1",
        policy_version="synthetic-offline.v1",
        permission_stamp={},
        provider_id="mock",
        request_fingerprint=b"b" * 32,
        idempotency_key=uuid.uuid4(),
        state=state,
        version=1 if terminal else 0,
        candidate_count=0 if state == "completed" else None,
        failure_code="SYNTHETIC_FAILURE" if state == "failed" else None,
        discard_reason={"discarded": "source_changed", "cancelled": "cancelled_by_owner"}.get(
            state
        ),
        finished_at=datetime.now(UTC) if terminal else None,
    )


def _candidate(graph, *, batch=None):
    return MemoryCandidate(
        family_member_id=graph.member.id,
        family_scope_id=graph.family.id,
        source_message_id=graph.message.id,
        source_scope_id=graph.message.id,
        origin="extraction" if batch else "manual",
        batch_id=batch.id if batch else None,
        batch_ordinal=1 if batch else None,
        created_by_user_id=graph.owner.id,
        version=0,
        revision_counter=0,
    )


def _revision(graph, *, candidate=None, memory=None, ordinal=1):
    return ContentRevision(
        candidate_id=candidate.id if candidate else None,
        memory_id=memory.id if memory else None,
        family_member_id=graph.member.id,
        family_scope_id=graph.family.id,
        source_message_id=graph.message.id,
        source_scope_id=graph.message.id,
        ordinal=ordinal,
        author_mode="manual",
        actor_user_id=graph.owner.id,
        derivation_profile="raw_manual",
        required_purposes=[],
        input_permission_stamp={},
        body_state="present",
        payload=_payload(),
        content_digest=b"d" * 32,
        digest_scheme="memory-content.v1",
        digest_key_id="synthetic-pg",
    )


def test_postgres_schema_constraints_match_workflow_metadata(db_session):
    inspector = inspect(db_session.connection())
    for model in (ExtractionBatch, MemoryCandidate, ContentRevision, RevisionProposal):
        table = model.__table__
        actual_columns = {column["name"]: column for column in inspector.get_columns(table.name)}
        assert set(actual_columns) == set(table.columns.keys())
        for column in table.columns:
            assert actual_columns[column.name]["nullable"] == column.nullable
        actual_checks = {row["name"] for row in inspector.get_check_constraints(table.name)}
        expected_checks = {
            constraint.name
            for constraint in table.constraints
            if constraint.__class__.__name__ == "CheckConstraint"
        }
        assert actual_checks == expected_checks
        actual_unique = {row["name"] for row in inspector.get_unique_constraints(table.name)}
        expected_unique = {
            constraint.name
            for constraint in table.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        }
        assert actual_unique == expected_unique
        actual_fk = {row["name"]: row for row in inspector.get_foreign_keys(table.name)}
        expected_fk = {constraint.name for constraint in table.foreign_key_constraints}
        assert set(actual_fk) == expected_fk
        assert all(row["options"].get("ondelete") == "RESTRICT" for row in actual_fk.values())
    revision_columns = {
        row["name"]: row for row in inspector.get_columns("memory_content_revisions")
    }
    assert revision_columns["payload"]["type"].__class__.__name__ == "JSONB"
    assert revision_columns["created_at"]["type"].timezone is True


@pytest.mark.parametrize("state", ["pending", "completed", "failed", "discarded", "cancelled"])
@pytest.mark.parametrize("target", ["interview", "member", "family"])
def test_postgres_zero_candidate_batch_restricts_parent_delete(db_session, state, target):
    graph = _graph(db_session)
    batch = _batch(graph, state)
    db_session.add(batch)
    db_session.commit()
    parent = getattr(graph, target)
    with pytest.raises(IntegrityError) as caught, db_session.begin_nested():
        db_session.execute(delete(type(parent)).where(type(parent).id == parent.id))
        db_session.flush()
    assert caught.value.orig.sqlstate == "23503"
    diagnostic = caught.value.orig.diag
    assert (diagnostic.table_name, diagnostic.constraint_name) in PROTECTED_DELETE_FK_MANIFEST
    db_session.expire_all()
    for record in (
        graph.family,
        graph.member,
        graph.interview,
        graph.session,
        graph.message,
        batch,
    ):
        assert db_session.get(type(record), record.id) is not None
    assert db_session.get(InterviewMessage, graph.message.id).content == "Synthetic source"
    assert db_session.get(ExtractionBatch, batch.id).state == state


def test_postgres_batch_subject_composite_fk_rejects_wrong_source(db_session):
    first, second = _graph(db_session), _graph(db_session)
    batch = _batch(first)
    db_session.add(batch)
    db_session.commit()
    with pytest.raises(IntegrityError) as caught, db_session.begin_nested():
        db_session.add(_candidate(second, batch=batch))
        db_session.flush()
    assert caught.value.orig.sqlstate == "23503"
    assert caught.value.orig.diag.constraint_name == "fk_mc_batch_subject"
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(MemoryCandidate)
            .where(MemoryCandidate.family_member_id.in_((first.member.id, second.member.id)))
        )
        == 0
    )


@pytest.mark.parametrize("target", ["none", "both"])
def test_postgres_revision_target_xor_check(db_session, target):
    graph = _graph(db_session)
    candidate = _candidate(graph)
    memory = Memory(
        family_member_id=graph.member.id,
        source_message_id=graph.message.id,
        title="Legacy synthetic",
        content="Legacy synthetic",
        record_origin="legacy",
    )
    db_session.add_all([candidate, memory])
    db_session.commit()
    row = _revision(
        graph,
        candidate=candidate if target == "both" else None,
        memory=memory if target == "both" else None,
    )
    with pytest.raises(IntegrityError) as caught, db_session.begin_nested():
        db_session.add(row)
        db_session.flush()
    assert caught.value.orig.sqlstate == "23514"
    assert caught.value.orig.diag.constraint_name == "ck_mcr_target"


def test_postgres_revision_subject_fk_rejects_cross_member(db_session):
    first, second = _graph(db_session), _graph(db_session)
    candidate = _candidate(first)
    db_session.add(candidate)
    db_session.commit()
    with pytest.raises(IntegrityError) as caught, db_session.begin_nested():
        db_session.add(_revision(second, candidate=candidate))
        db_session.flush()
    assert caught.value.orig.sqlstate == "23503"
    assert caught.value.orig.diag.constraint_name == "fk_mcr_candidate_subject"


def test_postgres_proposal_input_must_belong_to_target(db_session):
    graph = _graph(db_session)
    first, second = _candidate(graph), _candidate(graph)
    db_session.add_all([first, second])
    db_session.flush()
    revision = _revision(graph, candidate=first)
    db_session.add(revision)
    db_session.commit()
    with pytest.raises(IntegrityError) as caught, db_session.begin_nested():
        db_session.add(
            RevisionProposal(
                family_scope_id=graph.family.id,
                family_member_id=graph.member.id,
                candidate_id=second.id,
                memory_id=None,
                input_revision_id=revision.id,
                proposed_by_user_id=graph.owner.id,
                base_version=0,
                base_revision_id=None,
                payload_digest=b"d" * 32,
                digest_scheme="memory-content.v1",
                digest_key_id="synthetic-pg",
                state="draft",
                version=0,
            )
        )
        db_session.flush()
    assert caught.value.orig.sqlstate == "23503"
    assert caught.value.orig.diag.constraint_name in {
        "fk_rp_input_candidate",
        "fk_rp_input_candidate_member",
    }


def test_postgres_service_promotion_builds_exact_current_proof(db_session):
    graph = _graph(db_session)
    db_session.commit()
    policy, integrity = _capabilities(graph)
    created, status = memory_review.manual_candidate(
        db_session,
        graph.owner.id,
        graph.member.id,
        ManualCandidateCreate(source_message_id=graph.message.id, payload=_payload()),
        uuid.uuid4(),
        policy=policy,
        integrity=integrity,
    )
    assert status == 201
    memory_review.submit(
        db_session,
        graph.owner.id,
        created["proposal_id"],
        ProposalSubmit(expected_version=0, expected_target_version=0),
        uuid.uuid4(),
        policy=policy,
        integrity=integrity,
    )
    approved, status = memory_review.approve(
        db_session,
        graph.owner.id,
        created["proposal_id"],
        ProposalApprove(expected_version=1, expected_target_version=0),
        uuid.uuid4(),
        policy=policy,
        integrity=integrity,
    )
    assert status == 200
    memory = db_session.get(Memory, uuid.UUID(str(approved["memory_id"])))
    revision = db_session.get(ContentRevision, uuid.UUID(str(approved["memory_revision_id"])))
    proposal = db_session.get(RevisionProposal, uuid.UUID(str(created["proposal_id"])))
    assert (memory.current_revision_id, memory.current_approval_proposal_id) == (
        revision.id,
        proposal.id,
    )
    assert (proposal.result_memory_revision_id, proposal.result_memory_id) == (
        revision.id,
        memory.id,
    )
    assert memory.origin_candidate_id == uuid.UUID(str(created["candidate_id"]))
    assert revision.origin_revision_id == uuid.UUID(str(created["revision_id"]))
    assert revision.payload == _payload()
    assert memory.content is None and memory.title is None
    assert memory.version == 1 and proposal.state == "approved"


def test_postgres_section_has_exact_same_memory_proof(db_session):
    inspector = inspect(db_session.connection())
    constraints = {
        row["name"]: row for row in inspector.get_foreign_keys(MemoirSection.__tablename__)
    }
    assert constraints["fk_memoir_sections_proof"]["constrained_columns"] == [
        "approval_proposal_id",
        "memory_revision_id",
        "memory_id",
    ]
    assert constraints["fk_memoir_sections_proof"]["referred_columns"] == [
        "id",
        "result_memory_revision_id",
        "result_memory_id",
    ]
    assert constraints["fk_memoir_sections_revision_memory"]["options"]["ondelete"] == "RESTRICT"


def test_postgres_two_candidate_approvals_real_runner_connections(db_session, memory_b_allocation):
    """Explicit future multi-connection gate; no shared/uncommitted-fixture fake race."""
    if os.environ.get("MEMORY_B_MULTI_CONNECTION_RUN_ID") != str(memory_b_allocation.run_id):
        pytest.skip(
            "Real two-connection approval needs separate verified Manager/Runner authorization"
        )
    engine = db_session.get_bind().engine
    # This test creates its own random graph in the already verified run database.
    # It commits only those unique test rows so both Runner connections can see them.
    # Manager discards the exact allocated database after all tests and workers exit.
    with Session(engine, autoflush=False, expire_on_commit=False) as setup:
        graph = _graph(setup)
        setup.commit()
        policy, integrity = _capabilities(graph)
        first, _ = memory_review.manual_candidate(
            setup,
            graph.owner.id,
            graph.member.id,
            ManualCandidateCreate(source_message_id=graph.message.id, payload=_payload()),
            uuid.uuid4(),
            policy=policy,
            integrity=integrity,
        )
        candidate_id = uuid.UUID(str(first["candidate_id"]))
        second, _ = memory_review.create_candidate_revision(
            setup,
            graph.owner.id,
            candidate_id,
            RevisionCreate(
                expected_version=0, parent_revision_id=first["revision_id"], payload=_payload()
            ),
            uuid.uuid4(),
            policy=policy,
            integrity=integrity,
        )
        proposals = (uuid.UUID(str(first["proposal_id"])), uuid.UUID(str(second["proposal_id"])))
        for proposal_id in proposals:
            memory_review.submit(
                setup,
                graph.owner.id,
                proposal_id,
                ProposalSubmit(expected_version=0, expected_target_version=0),
                uuid.uuid4(),
                policy=policy,
                integrity=integrity,
            )
        owner_id = graph.owner.id
    barrier = threading.Barrier(2)
    results = Queue()

    def worker(proposal_id):
        with Session(engine, autoflush=False, expire_on_commit=False) as runner:
            runner.execute(text("SET LOCAL lock_timeout = '2s'"))
            runner.execute(text("SET LOCAL statement_timeout = '5s'"))
            barrier.wait(timeout=5)
            try:
                snapshot, status = memory_review.approve(
                    runner,
                    owner_id,
                    proposal_id,
                    ProposalApprove(expected_version=1, expected_target_version=0),
                    uuid.uuid4(),
                    policy=policy,
                    integrity=integrity,
                )
                results.put((status, snapshot["state"]))
            except AppException as error:
                results.put((error.status_code, error.code))

    threads = [
        threading.Thread(target=worker, args=(proposal,), daemon=False) for proposal in proposals
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    if any(thread.is_alive() for thread in threads):
        pytest.fail(
            "Runner thread outcome uncertain; stop and retain the allocated database for Manager review"
        )
    assert results.qsize() == 2
    outcomes = sorted([results.get_nowait(), results.get_nowait()])
    assert outcomes == [(200, "approved"), (409, "PROPOSAL_STALE")]
    with Session(engine) as verify:
        memories = verify.scalars(
            select(Memory).where(Memory.origin_candidate_id == candidate_id)
        ).all()
        assert len(memories) == 1
        states = verify.scalars(
            select(RevisionProposal.state).where(RevisionProposal.id.in_(proposals))
        ).all()
        assert sorted(states) == ["approved", "stale"]


@pytest.mark.parametrize("first", ["create", "clear"])
@pytest.mark.parametrize("target", ["proof", "body"])
def test_postgres_memoir_vs_synthetic_clear_two_commit_orders(
    db_session, memory_b_allocation, monkeypatch, first, target
):
    """SOURCE ONLY until Manager allocation and explicit multi-connection approval.

    Both actors use the same total order: command -> Memory -> Proposal -> Revision,
    UUID-sorted within each type. The clear fixture changes only proof/body rows:
    it has no command or Memory mutation, so locks only the Proposal/Revision
    subset in that order. It must serialize even without locking Memory.
    This is not a C6 endpoint or a production clearing/Consent implementation.
    """
    if os.environ.get("MEMORY_B_MULTI_CONNECTION_RUN_ID") != str(memory_b_allocation.run_id):
        pytest.skip("Memoir race requires verified Manager/Runner multi-connection authorization")
    engine = db_session.get_bind().engine
    with Session(engine, autoflush=False, expire_on_commit=False) as setup:
        graph = _graph(setup)
        setup.commit()
        policy, integrity = _capabilities(graph)
        candidate, _ = memory_review.manual_candidate(
            setup,
            graph.owner.id,
            graph.member.id,
            ManualCandidateCreate(source_message_id=graph.message.id, payload=_payload()),
            uuid.uuid4(),
            policy=policy,
            integrity=integrity,
        )
        memory_review.submit(
            setup,
            graph.owner.id,
            candidate["proposal_id"],
            ProposalSubmit(expected_version=0, expected_target_version=0),
            uuid.uuid4(),
            policy=policy,
            integrity=integrity,
        )
        approved, _ = memory_review.approve(
            setup,
            graph.owner.id,
            candidate["proposal_id"],
            ProposalApprove(expected_version=1, expected_target_version=0),
            uuid.uuid4(),
            policy=policy,
            integrity=integrity,
        )
        owner_id, member_id = graph.owner.id, graph.member.id
        memory_id = approved["memory_id"]
        proposal_id = approved["proposal_id"]
        revision_id = approved["memory_revision_id"]
        data = MemoirCreate(
            title="Synthetic serialized snapshot",
            sections=(
                {
                    "memory_id": memory_id,
                    "memory_revision_id": revision_id,
                    "approval_proposal_id": proposal_id,
                },
            ),
        )

    barrier = threading.Barrier(2)
    first_locked, second_attempt = threading.Event(), threading.Event()
    pids, outcomes = {}, Queue()
    original_gate = memoir_service._approved_gate
    command_key = uuid.uuid4()

    def observe_blocked_then_release(runner):
        first_locked.set()
        assert second_attempt.wait(timeout=5)
        other = "clear" if first == "create" else "create"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            waiting = runner.scalar(
                text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"),
                {"pid": pids[other]},
            )
            if waiting == "Lock":
                return
            time.sleep(0.01)
        raise AssertionError("Expected actual PostgreSQL lock wait was not observed")

    def gate(db, *args, **kwargs):
        if first == "create" and db.info.get("race_role") == "create":
            # Memoir now holds exact proof/body locks before any gate/body copy.
            observe_blocked_then_release(db)
        return original_gate(db, *args, **kwargs)

    monkeypatch.setattr(memoir_service, "_approved_gate", gate)

    def worker(role):
        try:
            with Session(engine, autoflush=False, expire_on_commit=False) as runner:
                runner.info["race_role"] = role
                runner.execute(text("SET LOCAL lock_timeout = '10s'"))
                runner.execute(text("SET LOCAL statement_timeout = '12s'"))
                pids[role] = runner.scalar(text("SELECT pg_backend_pid()"))

                def lock_attempt(state):
                    statement = state.statement
                    # A Memory lock alone cannot serialize proof/body-only clearing.
                    if (
                        role != first
                        and getattr(statement, "_for_update_arg", None) is not None
                        and "revision_proposals" in str(statement)
                    ):
                        second_attempt.set()

                event.listen(runner, "do_orm_execute", lock_attempt)
                try:
                    barrier.wait(timeout=5)
                    if role != first:
                        assert first_locked.wait(timeout=5)
                    if role == "create":
                        snapshot, status = memoir_service.create(
                            runner,
                            owner_id,
                            member_id,
                            data,
                            command_key,
                            policy=policy,
                            integrity=integrity,
                        )
                        outcomes.put((role, status, snapshot))
                    else:
                        memory = memory_review.owned_memory(runner, owner_id, memory_id)
                        proof = memory_review.owned(
                            runner, RevisionProposal, owner_id, proposal_id, lock=True
                        )
                        revision = memory_review.owned(
                            runner, ContentRevision, owner_id, revision_id, lock=True
                        )
                        assert proof.result_memory_id == memory.id
                        assert proof.result_memory_revision_id == revision.id
                        if target == "proof":
                            proof.state = "purged"
                            proof.payload_digest = proof.digest_scheme = proof.digest_key_id = None
                        else:
                            revision.body_state = "purged"
                            revision.payload = revision.content_digest = None
                            revision.digest_scheme = revision.digest_key_id = None
                        runner.flush()
                        if first == "clear":
                            observe_blocked_then_release(runner)
                        runner.commit()
                        outcomes.put((role, 200, "synthetic_clear_committed"))
                finally:
                    event.remove(runner, "do_orm_execute", lock_attempt)
        except AppException as exc:
            outcomes.put((role, exc.status_code, exc.code))
        except Exception as exc:  # noqa: BLE001 -- capture worker exit without private error text.
            outcomes.put((role, "unexpected", type(exc).__name__))

    threads = [
        threading.Thread(target=worker, args=(role,), daemon=False) for role in ("create", "clear")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=25)
    if any(thread.is_alive() for thread in threads):
        pytest.fail("Runner exit uncertain: STOP, retain database for trusted Manager review")
    assert outcomes.qsize() == 2
    results = {
        role: (status, result)
        for role, status, result in (outcomes.get_nowait(), outcomes.get_nowait())
    }
    assert results["clear"] == (200, "synthetic_clear_committed")
    assert pids["create"] != pids["clear"] and second_attempt.is_set()
    with Session(engine) as verify:
        sections = verify.scalars(
            select(MemoirSection).where(MemoirSection.memory_id == memory_id)
        ).all()
        if first == "create":
            status, snapshot = results["create"]
            assert status == 201 and len(sections) == 1
            assert verify.get(Memoir, snapshot["memoir_id"]) is not None
            assert sections[0].memory_revision_id == revision_id
            assert sections[0].approval_proposal_id == proposal_id
            assert sections[0].title == _payload()["title"]
            assert sections[0].content == _payload()["content"]
        else:
            assert results["create"] == (
                422 if target == "proof" else 403,
                "INVALID_APPROVED_REVISION" if target == "proof" else "CONTENT_RESTRICTED",
            )
            assert sections == []
            assert (
                verify.scalar(
                    select(func.count())
                    .select_from(Memoir)
                    .where(Memoir.family_member_id == member_id)
                )
                == 0
            )
            assert (
                verify.scalar(
                    select(func.count())
                    .select_from(CommandIdempotencyRecord)
                    .where(
                        CommandIdempotencyRecord.actor_user_id == owner_id,
                        CommandIdempotencyRecord.operation == "memory.memoir.create",
                        CommandIdempotencyRecord.idempotency_key == command_key,
                    )
                )
                == 0
            )
        if target == "proof":
            assert verify.get(RevisionProposal, proposal_id).state == "purged"
        else:
            body = verify.get(ContentRevision, revision_id)
            assert body.body_state == "purged" and body.payload is None
