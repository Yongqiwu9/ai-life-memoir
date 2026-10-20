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
from sqlalchemy import delete, event, func, inspect, select, text, update
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
    ExtractionCreate,
    ManualCandidateCreate,
    ProposalApprove,
    ProposalSubmit,
    RevisionCreate,
)
from app.services import memoir as memoir_service
from app.services import memory_extraction, memory_review
from app.services.ai_memory_client import DeterministicMockMemoryClient
from app.services.memory_integrity import MemoryIntegrity, SyntheticKeyProvider
from app.services.memory_policy import PURPOSES, DecisionStamp, SyntheticMemoryPolicy

pytestmark = pytest.mark.integration


DELTA_B34_CASES = {
    "current_missing_revision": ("23514", {("memories", "ck_memories_current_pair")}),
    "current_missing_proof": ("23514", {("memories", "ck_memories_current_pair")}),
    "current_cross_memory": ("23503", {("memories", "fk_memories_current_proof")}),
    "result_missing_memory": (
        "23514",
        {
            ("revision_proposals", "ck_rp_result_pair"),
            ("revision_proposals", "ck_rp_lifecycle"),
        },
    ),
    "result_missing_revision": ("23514", {("revision_proposals", "ck_rp_result_pair")}),
    "result_cross_memory": (
        "23503",
        {
            ("revision_proposals", "fk_rp_result_memory"),
            ("memories", "fk_memories_current_proof"),
        },
    ),
    "section_missing_revision": ("23514", {("memoir_sections", "ck_memoir_sections_proof_pair")}),
    "section_missing_proof": ("23514", {("memoir_sections", "ck_memoir_sections_proof_pair")}),
    "section_cross_revision": (
        "23503",
        {
            ("memoir_sections", "fk_memoir_sections_revision_memory"),
            ("memoir_sections", "fk_memoir_sections_proof"),
        },
    ),
    "section_cross_proof": ("23503", {("memoir_sections", "fk_memoir_sections_proof")}),
}


def _delta_pg_snapshot(db):
    from app.database.base import Base

    return {
        table.name: [
            dict(row) for row in db.execute(select(table).order_by(*table.primary_key)).mappings()
        ]
        for table in Base.metadata.sorted_tables
    }


@pytest.mark.parametrize("violation", list(DELTA_B34_CASES))
def test_delta_b34_postgres_reference_constraints(db_session, violation):
    """Real Core negative writes, with valid service-created proofs and savepoint rollback."""
    db = db_session
    graph = _graph(db)
    db.commit()
    policy, integrity = _capabilities(graph)
    approvals = []
    for _ in range(2):
        created, _ = memory_review.manual_candidate(
            db,
            graph.owner.id,
            graph.member.id,
            ManualCandidateCreate(source_message_id=graph.message.id, payload=_payload()),
            uuid.uuid4(),
            policy=policy,
            integrity=integrity,
        )
        memory_review.submit(
            db,
            graph.owner.id,
            created["proposal_id"],
            ProposalSubmit(expected_version=0, expected_target_version=0),
            uuid.uuid4(),
            policy=policy,
            integrity=integrity,
        )
        approved, _ = memory_review.approve(
            db,
            graph.owner.id,
            created["proposal_id"],
            ProposalApprove(expected_version=1, expected_target_version=0),
            uuid.uuid4(),
            policy=policy,
            integrity=integrity,
        )
        approvals.append(
            {
                "memory": uuid.UUID(str(approved["memory_id"])),
                "revision": uuid.UUID(str(approved["memory_revision_id"])),
                "proof": uuid.UUID(str(created["proposal_id"])),
            }
        )
    first, second = approvals
    section_id = None
    if violation.startswith("section_"):
        memoir, _ = memoir_service.create(
            db,
            graph.owner.id,
            graph.member.id,
            MemoirCreate(
                title="Synthetic constraint fixture",
                sections=[
                    {
                        "memory_id": first["memory"],
                        "memory_revision_id": first["revision"],
                        "approval_proposal_id": first["proof"],
                    }
                ],
            ),
            uuid.uuid4(),
            policy=policy,
            integrity=integrity,
        )
        section_id = uuid.UUID(str(memoir["section_ids"][0]))
    statements = {
        "current_missing_revision": update(Memory)
        .where(Memory.id == first["memory"])
        .values(current_revision_id=None),
        "current_missing_proof": update(Memory)
        .where(Memory.id == first["memory"])
        .values(current_approval_proposal_id=None),
        "current_cross_memory": update(Memory)
        .where(Memory.id == first["memory"])
        .values(
            current_revision_id=second["revision"],
            current_approval_proposal_id=second["proof"],
        ),
        "result_missing_memory": update(RevisionProposal)
        .where(RevisionProposal.id == first["proof"])
        .values(result_memory_id=None),
        "result_missing_revision": update(RevisionProposal)
        .where(RevisionProposal.id == first["proof"])
        .values(result_memory_revision_id=None),
        "result_cross_memory": update(RevisionProposal)
        .where(RevisionProposal.id == first["proof"])
        .values(result_memory_id=second["memory"]),
        "section_missing_revision": update(MemoirSection)
        .where(MemoirSection.id == section_id)
        .values(memory_revision_id=None),
        "section_missing_proof": update(MemoirSection)
        .where(MemoirSection.id == section_id)
        .values(approval_proposal_id=None),
        "section_cross_revision": update(MemoirSection)
        .where(MemoirSection.id == section_id)
        .values(memory_revision_id=second["revision"]),
        "section_cross_proof": update(MemoirSection)
        .where(MemoirSection.id == section_id)
        .values(approval_proposal_id=second["proof"]),
    }
    before = _delta_pg_snapshot(db)
    with pytest.raises(IntegrityError) as caught, db.begin_nested():
        db.execute(statements[violation].execution_options(synchronize_session=False))
        db.flush()
    expected_state, expected_pairs = DELTA_B34_CASES[violation]
    diagnostic = caught.value.orig.diag
    assert caught.value.orig.sqlstate == expected_state
    assert (diagnostic.table_name, diagnostic.constraint_name) in expected_pairs
    db.expire_all()
    assert _delta_pg_snapshot(db) == before
    assert (
        db.scalar(select(InterviewMessage.content).where(InterviewMessage.id == graph.message.id))
        == graph.message.content
    )


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
        if head != ["c296a4e8d102"]:
            raise pytest.UsageError(
                "Allocated test schema is not at the exact project migration head c296a4e8d102"
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


def _supp_multi_connection_gate(allocation):
    if os.environ.get("MEMORY_B_MULTI_CONNECTION_RUN_ID") != str(allocation.run_id):
        pytest.skip("Supplement requires verified Manager/Runner multi-connection authorization")


def _supp_seed(engine, *, promote=False):
    with Session(engine, autoflush=False, expire_on_commit=False) as db:
        graph = _graph(db)
        db.commit()
        policy, integrity = _capabilities(graph)
        created, status = memory_review.manual_candidate(
            db,
            graph.owner.id,
            graph.member.id,
            ManualCandidateCreate(source_message_id=graph.message.id, payload=_payload()),
            uuid.uuid4(),
            policy=policy,
            integrity=integrity,
        )
        assert status == 201
        if promote:
            memory_review.submit(
                db,
                graph.owner.id,
                created["proposal_id"],
                ProposalSubmit(expected_version=0, expected_target_version=0),
                uuid.uuid4(),
                policy=policy,
                integrity=integrity,
            )
            created, status = memory_review.approve(
                db,
                graph.owner.id,
                created["proposal_id"],
                ProposalApprove(expected_version=1, expected_target_version=0),
                uuid.uuid4(),
                policy=policy,
                integrity=integrity,
            )
            assert status == 200
        return graph, policy, integrity, created


def _supp_serialized_workers(engine, monkeypatch, *, candidate, command):
    """Observe actual server lock blocking at the service's own target lock."""
    barrier = threading.Barrier(2)
    held, attempted = threading.Event(), threading.Event()
    pids, outcomes = {}, Queue()
    original = memory_review.owned if candidate else memory_review.owned_memory
    table = "memory_candidates" if candidate else "memories"

    def owned(db, *args, **kwargs):
        result = original(db, *args, **kwargs)
        if kwargs.get("lock") and db.info.get("supp_worker") == 0:
            if candidate and args[0] is not MemoryCandidate:
                return result
            held.set()
            assert attempted.wait(5)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                blockers = db.scalar(text("SELECT pg_blocking_pids(:pid)"), {"pid": pids[1]})
                if pids[0] in blockers:
                    return result
                time.sleep(0.01)
            raise AssertionError("Actual target lock blocking not observed")
        return result

    monkeypatch.setattr(memory_review, "owned" if candidate else "owned_memory", owned)

    def worker(index):
        try:
            with Session(engine, autoflush=False, expire_on_commit=False) as db:
                db.info["supp_worker"] = index
                db.execute(text("SET LOCAL lock_timeout = '10s'"))
                db.execute(text("SET LOCAL statement_timeout = '12s'"))
                pids[index] = db.scalar(text("SELECT pg_backend_pid()"))

                def before_execute(state):
                    if (
                        index == 1
                        and getattr(state.statement, "_for_update_arg", None) is not None
                        and table in str(state.statement)
                    ):
                        attempted.set()

                event.listen(db, "do_orm_execute", before_execute)
                try:
                    barrier.wait(5)
                    if index == 1:
                        assert held.wait(5)
                    snapshot, status = command(db, index)
                    outcomes.put((index, status, snapshot))
                finally:
                    event.remove(db, "do_orm_execute", before_execute)
        except AppException as exc:
            outcomes.put((index, exc.status_code, exc.code))
        except Exception as exc:  # noqa: BLE001 -- no private driver error text.
            outcomes.put((index, "unexpected", type(exc).__name__))

    threads = [threading.Thread(target=worker, args=(i,), daemon=False) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(25)
    if any(thread.is_alive() for thread in threads):
        pytest.fail("Runner exit uncertain: STOP and retain allocation for Manager review")
    assert len(pids) == 2 and pids[0] != pids[1]
    assert outcomes.qsize() == 2 and held.is_set() and attempted.is_set()
    return {i: (status, result) for i, status, result in (outcomes.get(), outcomes.get())}


def test_postgres_provider_call_releases_parent_locks(db_session, memory_b_allocation):
    _supp_multi_connection_gate(memory_b_allocation)
    engine = db_session.get_bind().engine
    # Keep the caller's physical connection checked out after reserve commit;
    # a second Runner cannot merely reuse the same idle pool connection.
    with (
        engine.connect() as connection,
        Session(connection, autoflush=False, expire_on_commit=False) as caller,
    ):
        graph = _graph(caller)
        caller.commit()
        policy, integrity = _capabilities(graph)
        caller_pid = caller.scalar(text("SELECT pg_backend_pid()"))
        caller.rollback()
        observed = []
        key = uuid.uuid4()

        class Client:
            provider_id = "mock"

            def extract(self, request):
                assert not caller.in_transaction()
                with Session(engine) as other:
                    pid = other.scalar(text("SELECT pg_backend_pid()"))
                    assert pid != caller_pid
                    assert other.execute(text("SELECT current_database(), current_user")).one() == (
                        memory_b_allocation.database,
                        memory_b_allocation.runner,
                    )
                    for row in (
                        graph.family,
                        graph.member,
                        graph.interview,
                        graph.session,
                        graph.message,
                    ):
                        assert (
                            other.scalar(
                                select(type(row))
                                .where(type(row).id == row.id)
                                .with_for_update(nowait=True)
                            )
                            is not None
                        )
                    assert (
                        other.scalar(
                            select(ExtractionBatch)
                            .where(ExtractionBatch.id == request.request_id)
                            .with_for_update(nowait=True)
                        ).state
                        == "pending"
                    )
                    command = other.scalar(
                        select(CommandIdempotencyRecord)
                        .where(
                            CommandIdempotencyRecord.actor_user_id == graph.owner.id,
                            CommandIdempotencyRecord.idempotency_key == key,
                        )
                        .with_for_update(nowait=True)
                    )
                    assert command is not None and command.state == "processing"
                    observed.append(pid)
                return DeterministicMockMemoryClient().extract(request)

        result, status = memory_extraction.start(
            caller,
            graph.owner.id,
            graph.session.id,
            ExtractionCreate(source_message_id=graph.message.id),
            key,
            policy=policy,
            integrity=integrity,
            client=Client(),
        )
        assert status == 201 and result["state"] == "completed"
        assert result["candidate_count"] == 1 and len(observed) == 1
        assert caller.get(InterviewMessage, graph.message.id).content == "Synthetic source"


@pytest.mark.parametrize("target", ["candidate", "memory"])
def test_postgres_revision_ordinals_real_runner_connections(
    db_session, memory_b_allocation, monkeypatch, target
):
    _supp_multi_connection_gate(memory_b_allocation)
    engine = db_session.get_bind().engine
    graph, policy, integrity, created = _supp_seed(engine, promote=target == "memory")
    target_id = created["candidate_id" if target == "candidate" else "memory_id"]
    parent_id = created["revision_id" if target == "candidate" else "memory_revision_id"]
    version = 0 if target == "candidate" else 1

    def command(db, index):
        method = (
            memory_review.create_candidate_revision
            if target == "candidate"
            else memory_review.create_memory_revision
        )
        return method(
            db,
            graph.owner.id,
            target_id,
            RevisionCreate(
                expected_version=version,
                parent_revision_id=parent_id,
                payload={**_payload(), "title": f"Synthetic revision {index}"},
            ),
            uuid.uuid4(),
            policy=policy,
            integrity=integrity,
        )

    results = _supp_serialized_workers(
        engine, monkeypatch, candidate=target == "candidate", command=command
    )
    assert [result[0] for result in results.values()] == [201, 201]
    with Session(engine) as verify:
        model = MemoryCandidate if target == "candidate" else Memory
        row = verify.get(model, target_id)
        assert row.version == version and row.revision_counter == 3
        field = ContentRevision.candidate_id if target == "candidate" else ContentRevision.memory_id
        revisions = verify.scalars(select(ContentRevision).where(field == target_id)).all()
        assert sorted(item.ordinal for item in revisions) == [1, 2, 3]
        assert all(item.source_scope_id == graph.message.id for item in revisions)
        if target == "memory":
            assert row.current_revision_id == parent_id
        else:
            assert row.promoted_memory_id is None


def test_postgres_two_memory_approvals_real_runner_connections(
    db_session, memory_b_allocation, monkeypatch
):
    _supp_multi_connection_gate(memory_b_allocation)
    engine = db_session.get_bind().engine
    graph, policy, integrity, approved = _supp_seed(engine, promote=True)
    with Session(engine, autoflush=False, expire_on_commit=False) as setup:
        proposals = []
        for index in range(2):
            result, _ = memory_review.create_memory_revision(
                setup,
                graph.owner.id,
                approved["memory_id"],
                RevisionCreate(
                    expected_version=1,
                    parent_revision_id=approved["memory_revision_id"],
                    payload={**_payload(), "title": f"Synthetic approval {index}"},
                ),
                uuid.uuid4(),
                policy=policy,
                integrity=integrity,
            )
            memory_review.submit(
                setup,
                graph.owner.id,
                result["proposal_id"],
                ProposalSubmit(expected_version=0, expected_target_version=1),
                uuid.uuid4(),
                policy=policy,
                integrity=integrity,
            )
            proposals.append(result["proposal_id"])

    def command(db, index):
        return memory_review.approve(
            db,
            graph.owner.id,
            proposals[index],
            ProposalApprove(expected_version=1, expected_target_version=1),
            uuid.uuid4(),
            policy=policy,
            integrity=integrity,
        )

    results = _supp_serialized_workers(engine, monkeypatch, candidate=False, command=command)
    assert results[0][0] == 200 and results[1] == (409, "PROPOSAL_STALE")
    with Session(engine) as verify:
        memory = verify.get(Memory, approved["memory_id"])
        proof = verify.get(RevisionProposal, proposals[0])
        assert memory.version == 2 and memory.revision_counter == 3
        assert memory.current_revision_id == proof.result_memory_revision_id
        assert memory.current_approval_proposal_id == proof.id
        assert proof.result_memory_id == memory.id and proof.state == "approved"
        stale = verify.get(RevisionProposal, proposals[1])
        assert stale.state == "stale" and stale.result_memory_revision_id is None
        assert verify.get(InterviewMessage, graph.message.id).content == "Synthetic source"


@pytest.mark.parametrize("target", ["interview", "member", "family"])
def test_postgres_parent_delete_vs_new_reference_real_runner_connections(
    db_session, memory_b_allocation, monkeypatch, target
):
    """Real immediate FK race, not a manufactured deferred/commit-time FK."""
    from app.crud import memory_workflow as workflow_crud
    from app.services import family, family_member, interview

    _supp_multi_connection_gate(memory_b_allocation)
    engine = db_session.get_bind().engine
    with Session(engine, autoflush=False, expire_on_commit=False) as setup:
        graph = _graph(setup)
        setup.commit()
    prechecked, inserted = threading.Event(), threading.Event()
    barrier = threading.Barrier(2)
    pids, errors, results = {}, [], Queue()
    original = workflow_crud.has_workflow_references

    def check(db, **kwargs):
        answer = original(db, **kwargs)
        if db.info.get("supp_delete") and not prechecked.is_set():
            assert answer is False
            prechecked.set()
            assert inserted.wait(5)
        return answer

    def record_error(context):
        orig = context.original_exception
        if getattr(orig, "sqlstate", None) == "23503":
            errors.append((orig.sqlstate, orig.diag.table_name, orig.diag.constraint_name))

    monkeypatch.setattr(workflow_crud, "has_workflow_references", check)
    event.listen(engine, "handle_error", record_error)

    def worker(role):
        try:
            with Session(engine, autoflush=False, expire_on_commit=False) as db:
                db.execute(text("SET LOCAL lock_timeout = '10s'"))
                db.execute(text("SET LOCAL statement_timeout = '12s'"))
                pids[role] = db.scalar(text("SELECT pg_backend_pid()"))
                barrier.wait(5)
                if role == "insert":
                    assert prechecked.wait(5)
                    batch = _batch(graph)
                    db.add(batch)
                    db.commit()
                    inserted.set()
                    results.put((role, 201, batch.id))
                else:
                    db.info["supp_delete"] = True
                    if target == "family":
                        family.delete_family(db, user_id=graph.owner.id, family_id=graph.family.id)
                    elif target == "member":
                        family_member.delete_family_member(
                            db,
                            user_id=graph.owner.id,
                            family_id=graph.family.id,
                            member_id=graph.member.id,
                        )
                    else:
                        interview.delete_interview(
                            db, user_id=graph.owner.id, interview_id=graph.interview.id
                        )
                    results.put((role, "unexpected_success", None))
        except AppException as exc:
            results.put((role, exc.status_code, exc.code))
        except Exception as exc:  # noqa: BLE001 -- fixed worker outcome only.
            results.put((role, "unexpected", type(exc).__name__))

    threads = [
        threading.Thread(target=worker, args=(role,), daemon=False) for role in ("delete", "insert")
    ]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(25)
        if any(thread.is_alive() for thread in threads):
            pytest.fail("Runner exit uncertain: STOP and retain allocation for Manager review")
    finally:
        event.remove(engine, "handle_error", record_error)
    assert pids["delete"] != pids["insert"] and inserted.is_set()
    assert results.qsize() == 2
    outcomes = {role: (status, result) for role, status, result in (results.get(), results.get())}
    assert outcomes["delete"] == (409, "RESOURCE_IN_USE") and outcomes["insert"][0] == 201
    assert errors and all(
        code == "23503" and (table, name) in PROTECTED_DELETE_FK_MANIFEST
        for code, table, name in errors
    )
    with Session(engine) as verify:
        assert verify.get(ExtractionBatch, outcomes["insert"][1]).state == "pending"
        for row in (graph.family, graph.member, graph.interview, graph.session, graph.message):
            assert verify.get(type(row), row.id) is not None
        assert verify.get(InterviewMessage, graph.message.id).content == "Synthetic source"


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
