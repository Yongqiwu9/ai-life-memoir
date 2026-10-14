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
                str(Path(__file__).with_name("test_memory_memoir.py")),
                *sys.argv[1:],
            ]
        )
    )

import json
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import create_engine, event, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.core.memory_http import is_memory_path, memory_exception_response
from app.crud import memory_workflow as workflow_crud
from app.database import models_import  # noqa: F401
from app.database.base import Base
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
from app.schemas.memoir import MemoirContent, MemoirCreate, MemoirSectionContent
from app.schemas.memory_workflow import (
    CandidateRead,
    ExtractionBatchRead,
    ExtractionCommandResult,
    ExtractionCreate,
    ManualCandidateCreate,
    MemoirCreated,
    MemoryCommandResult,
    MemoryExtractionResult,
    ProposalApprove,
    ProposalCommandResult,
    ProposalRead,
    ProposalReject,
    ProposalSubmit,
    RevisionContent,
    RevisionCreate,
    RevisionCreated,
    RevisionList,
    RevisionPayload,
    VersionCommand,
)
from app.services import command_idempotency as commands
from app.services import family as family_service
from app.services import family_member as member_service
from app.services import interview as interview_service
from app.services import memoir as memoir_service
from app.services import memory as memory_service
from app.services import memory_extraction as extraction
from app.services import memory_review as review
from app.services.ai_memory_client import DeterministicMockMemoryClient, UnavailableMemoryClient
from app.services.memory_integrity import (
    MemoryIntegrity,
    SyntheticKeyProvider,
    canonical_bytes,
)
from app.services.memory_policy import (
    PURPOSES,
    DecisionStamp,
    SyntheticMemoryPolicy,
)


def payload(content=" 合成：小时候常在河边坐着。 "):
    return RevisionPayload(
        title=" 合成片段 ",
        content=content,
        time_text=None,
        place=None,
        emotion=None,
        uncertainties=(),
    )


@pytest.fixture
def records():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False, autoflush=False)
    user = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@synthetic.test", password_hash="synthetic")
    other = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@synthetic.test", password_hash="synthetic")
    db.add_all([user, other])
    db.flush()
    family = Family(id=uuid.uuid4(), owner_id=user.id, name="合成Family")
    db.add(family)
    db.flush()
    member = FamilyMember(id=uuid.uuid4(), family_id=family.id, name="合成人物")
    db.add(member)
    db.flush()
    interview = Interview(id=uuid.uuid4(), family_member_id=member.id, title="合成Interview")
    db.add(interview)
    db.flush()
    session = InterviewSession(id=uuid.uuid4(), interview_id=interview.id, status="completed")
    db.add(session)
    db.flush()
    source = InterviewMessage(
        id=uuid.uuid4(),
        session_id=session.id,
        role="user",
        source="text",
        sequence=1,
        content=" 合成：小时候常在河边坐着。 ",
    )
    db.add(source)
    db.commit()
    stamp = DecisionStamp(
        operation="fixture",
        actor_user_id=user.id,
        family_scope_id=family.id,
        family_member_id=member.id,
        source_scope_id=source.id,
        source_generation=1,
        required_purposes=tuple(sorted(PURPOSES)),
        purpose_generations={purpose: 1 for purpose in PURPOSES},
        allow=True,
        body_available=True,
        restore_verified=True,
    )
    policy = SyntheticMemoryPolicy({source.id: stamp})
    keys = SyntheticKeyProvider({"old": b"x" * 32, "new": b"y" * 32}, "old")
    bundle = SimpleNamespace(
        db=db,
        engine=engine,
        user=user,
        other=other,
        family=family,
        member=member,
        interview=interview,
        session=session,
        source=source,
        policy=policy,
        keys=keys,
        integrity=MemoryIntegrity(keys),
        client=DeterministicMockMemoryClient(),
    )
    try:
        yield bundle
    finally:
        db.rollback()
        db.close()
        engine.dispose()


def manual(r, body=None, key=None):
    return review.manual_candidate(
        r.db,
        r.user.id,
        r.member.id,
        ManualCandidateCreate(source_message_id=r.source.id, payload=body or payload()),
        key or uuid.uuid4(),
        policy=r.policy,
        integrity=r.integrity,
    )[0]


def submit(r, created):
    return review.submit(
        r.db,
        r.user.id,
        created["proposal_id"],
        ProposalSubmit(expected_version=0, expected_target_version=created["version"]),
        uuid.uuid4(),
        policy=r.policy,
        integrity=r.integrity,
    )[0]


def approve(r, created):
    submit(r, created)
    return review.approve(
        r.db,
        r.user.id,
        created["proposal_id"],
        ProposalApprove(expected_version=1, expected_target_version=created["version"]),
        uuid.uuid4(),
        policy=r.policy,
        integrity=r.integrity,
    )[0]


def extract(r, client=None, key=None):
    return extraction.start(
        r.db,
        r.user.id,
        r.session.id,
        ExtractionCreate(source_message_id=r.source.id),
        key or uuid.uuid4(),
        policy=r.policy,
        integrity=r.integrity,
        client=client or r.client,
    )[0]


def error(code, fn):
    with pytest.raises(AppException) as caught:
        fn()
    assert caught.value.code == code
    return caught.value


def count(r, model):
    return r.db.scalar(select(func.count()).select_from(model))


def test_b01_fk_on_and_per_case_synthetic(records):
    assert records.db.scalar(text("PRAGMA foreign_keys")) == 1
    assert count(records, MemoryCandidate) == 0


def test_b07_b09_extraction_from_completed_session_no_auto_memory(records):
    r = records
    original = r.source.content
    result = extract(r)
    assert result["state"] == "completed" and result["candidate_count"] == 1
    assert count(r, Memory) == 0
    created = review.get_candidate(r.db, r.user.id, result["candidate_ids"][0])
    assert created["origin"] == "extraction"
    assert len(created["revision_ids"]) == len(created["proposal_ids"]) == 1
    assert r.db.get(InterviewMessage, r.source.id).content == original


@pytest.mark.parametrize("number", [0, 2, 20])
def test_b09_all_output_cardinalities(records, number):
    r = records

    class Provider:
        provider_id = "mock"

        def extract(self, request):
            return MemoryExtractionResult(
                request_id=request.request_id,
                contract_version=request.contract_version,
                source_message_id=request.source_message_id,
                candidates=tuple(payload() for _ in range(number)),
            )

    result = extract(r, Provider())
    assert result["state"] == "completed" and result["candidate_count"] == number
    assert count(r, ContentRevision) == number and count(r, Memory) == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("content", " "),
        ("content", "x" * 20001),
        ("title", "x" * 201),
        ("time_text", 1),
        ("emotion", True),
        ("confidence", 0.9),
    ],
)
def test_b10_strict_payload_rejects(records, field, value):
    values = payload().model_dump()
    values[field] = value
    with pytest.raises(ValidationError):
        RevisionPayload.model_validate(values)


def test_b10_echo_and_output_extras_are_invalid(records):
    r = records

    class Bad:
        provider_id = "mock"

        def extract(self, request):
            return {
                "request_id": str(uuid.uuid4()),
                "contract_version": request.contract_version,
                "source_message_id": str(request.source_message_id),
                "candidates": [],
                "confidence": 1,
            }

    error("AI_INVALID_RESPONSE", lambda: extract(r, Bad()))
    assert count(r, MemoryCandidate) == 0
    assert r.db.scalar(select(ExtractionBatch.state)) == "failed"


@pytest.mark.parametrize("value", ["x" * 10001, " "])
def test_b10_source_size_no_truncate(records, value):
    r = records
    r.source.content = value
    r.db.commit()
    error("SOURCE_TOO_LARGE" if len(value) > 10000 else "INVALID_SOURCE", lambda: extract(r))
    assert count(r, ExtractionBatch) == 0


def test_b11_content_spaces_unicode_exact(records):
    r = records
    text_value = " Ａ\u0301 合成\u200b  "
    created = manual(r, payload(text_value))
    body = review.get_revision_content(
        r.db, r.user.id, created["revision_id"], policy=r.policy, integrity=r.integrity
    )
    assert body["payload"]["content"] == text_value
    approved = approve(r, created)
    current = memory_service.get(
        r.db, r.user.id, approved["memory_id"], policy=r.policy, integrity=r.integrity
    )
    assert current["current_content"]["content"] == text_value


def test_b12_terminal_and_new_batch_replay(records):
    r = records
    calls = []

    class Provider:
        provider_id = "mock"

        def extract(self, request):
            calls.append(request.request_id)
            return r.client.extract(request)

    key = uuid.uuid4()
    first = extract(r, Provider(), key)
    second = extract(r, Provider(), key)
    assert json.dumps(first, default=str, sort_keys=True) == json.dumps(
        second, default=str, sort_keys=True
    )
    assert len(calls) == 1
    third = extract(r, Provider())
    assert third["batch_id"] != first["batch_id"]
    assert count(r, MemoryCandidate) == 2


def test_b14_sensitive_replay_and_changed_payload_conflict(records):
    r = records
    key = uuid.uuid4()
    first = manual(r, key=key)
    assert json.dumps(manual(r, key=key), default=str, sort_keys=True) == json.dumps(
        first, default=str, sort_keys=True
    )
    error("IDEMPOTENCY_CONFLICT", lambda: manual(r, payload("合成不同"), key))
    assert count(r, MemoryCandidate) == 1


def test_b15_canonical_preserves_null_lists_text_and_no_float():
    assert canonical_bytes({"a": None}) != canonical_bytes({"a": ""})
    assert canonical_bytes({"a": ["a", "b"]}) != canonical_bytes({"a": ["b", "a"]})
    assert canonical_bytes({"a": " x "}) != canonical_bytes({"a": "x"})
    with pytest.raises(ValueError):
        canonical_bytes({"a": 1.0})


def test_b16_rotation_historical_key_and_missing_key(records):
    r = records
    key = uuid.uuid4()
    first = manual(r, key=key)
    r.keys.current_key_id = "new"
    assert json.dumps(manual(r, key=key), default=str, sort_keys=True) == json.dumps(
        first, default=str, sort_keys=True
    )
    r.keys.keys.pop("old")
    error("MEMORY_INTEGRITY_UNAVAILABLE", lambda: manual(r, key=key))
    assert count(r, MemoryCandidate) == 1


def test_b17_snapshots_no_sensitive_body(records):
    r = records
    created = manual(r)
    approve(r, created)
    for record in r.db.scalars(select(CommandIdempotencyRecord)):
        serialized = json.dumps(record.response_body, default=str)
        assert "合成片段" not in serialized and "河边" not in serialized
        assert "payload" not in serialized and "digest" not in serialized
    assert r.db.get(InterviewMessage, r.source.id).content.startswith(" 合成")


def test_b18_timeout_is_reported_classification_only(records):
    r = records

    class Timeout:
        provider_id = "mock"

        def extract(self, request):
            raise TimeoutError("sensitive synthetic source must not escape")

    failure = error("AI_PROVIDER_TIMEOUT", lambda: extract(r, Timeout()))
    assert failure.status_code == 503 and "sensitive" not in str(failure)
    assert r.db.scalar(select(ExtractionBatch.failure_code)) == "AI_PROVIDER_TIMEOUT"
    assert count(r, MemoryCandidate) == 0


def test_b20_provider_has_no_transaction_and_only_frozen_source(records):
    r = records

    class Provider:
        provider_id = "mock"

        def extract(self, request):
            assert not r.db.in_transaction()
            assert set(request.model_dump()) == {
                "request_id",
                "contract_version",
                "source_message_id",
                "source_text",
            }
            assert request.source_text == " 合成：小时候常在河边坐着。 "
            return r.client.extract(request)

    extract(r, Provider())


def test_b21_cancel_in_call_without_policy_or_key_late_result(records):
    r = records

    class Provider:
        provider_id = "mock"

        def extract(self, request):
            r.keys.keys.clear()
            result = extraction.cancel_batch(
                r.db,
                r.user.id,
                request.request_id,
                VersionCommand(expected_version=0),
                uuid.uuid4(),
            )
            assert result[0]["state"] == "cancelled"
            return r.client.extract(request)

    result = extract(r, Provider())
    assert result["state"] == "cancelled" and count(r, MemoryCandidate) == 0


@pytest.mark.parametrize("mode", ["source", "purpose"])
def test_b22_changed_context_discarded(records, mode):
    r = records

    class Provider:
        provider_id = "mock"

        def extract(self, request):
            if mode == "source":
                r.db.execute(
                    update(InterviewMessage)
                    .where(InterviewMessage.id == r.source.id)
                    .values(content="合成变更")
                )
                r.db.commit()
            else:
                original = r.policy.decisions[r.source.id]
                generations = dict(original.purpose_generations)
                generations["ai_analysis"] += 1
                r.policy.decisions[r.source.id] = original.model_copy(
                    update={"purpose_generations": generations}
                )
            return r.client.extract(request)

    result = extract(r, Provider())
    assert result["state"] == "discarded" and count(r, MemoryCandidate) == 0


def test_b24_b30_no_auto_approval_then_exact_promotion(records):
    r = records
    created = manual(r)
    assert count(r, Memory) == 0
    result = approve(r, created)
    parent = r.db.get(ContentRevision, created["revision_id"])
    output = r.db.get(ContentRevision, result["memory_revision_id"])
    assert parent.payload == output.payload and parent.content_digest == output.content_digest
    assert output.origin_revision_id == parent.id and output.candidate_id is None
    assert r.db.get(Memory, result["memory_id"]).content is None


def test_b25_ai_dependency_survives_manual_revision(records):
    r = records
    result = extract(r)
    candidate = review.get_candidate(r.db, r.user.id, result["candidate_ids"][0])
    created, status = review.create_candidate_revision(
        r.db,
        r.user.id,
        candidate["id"],
        RevisionCreate(
            expected_version=0,
            parent_revision_id=candidate["revision_ids"][0],
            payload=payload("合成人工整理"),
        ),
        uuid.uuid4(),
        policy=r.policy,
        integrity=r.integrity,
    )
    revision = r.db.get(ContentRevision, created["revision_id"])
    assert status == 201 and revision.author_mode == "manual"
    assert (
        "ai_analysis" in revision.required_purposes and revision.derivation_profile == "ai_derived"
    )


@pytest.mark.parametrize("transition", ["approve", "reject"])
def test_b27_draft_cannot_approve_or_reject(records, transition):
    r = records
    created = manual(r)
    fn = review.approve if transition == "approve" else review.reject
    data = (
        ProposalApprove(expected_version=0, expected_target_version=0)
        if transition == "approve"
        else ProposalReject(expected_version=0)
    )
    error(
        "PROPOSAL_STATE_CONFLICT",
        lambda: fn(
            r.db,
            r.user.id,
            created["proposal_id"],
            data,
            uuid.uuid4(),
            **({"policy": r.policy, "integrity": r.integrity} if transition == "approve" else {}),
        ),
    )
    assert count(r, Memory) == 0


def test_b28_submitted_text_is_not_overwritten(records):
    r = records
    first = manual(r)
    submit(r, first)
    second, status = review.create_candidate_revision(
        r.db,
        r.user.id,
        first["candidate_id"],
        RevisionCreate(
            expected_version=0, parent_revision_id=first["revision_id"], payload=payload("合成新稿")
        ),
        uuid.uuid4(),
        policy=r.policy,
        integrity=r.integrity,
    )
    assert status == 201 and second["proposal_id"] != first["proposal_id"]
    assert r.db.get(ContentRevision, first["revision_id"]).payload["content"] == payload().content


def test_b31_candidate_single_promotion_stales_other(records):
    r = records
    first = manual(r)
    second, _ = review.create_candidate_revision(
        r.db,
        r.user.id,
        first["candidate_id"],
        RevisionCreate(
            expected_version=0,
            parent_revision_id=first["revision_id"],
            payload=payload("合成第二稿"),
        ),
        uuid.uuid4(),
        policy=r.policy,
        integrity=r.integrity,
    )
    submit(r, first)
    submit(r, second)
    approved, _ = review.approve(
        r.db,
        r.user.id,
        first["proposal_id"],
        ProposalApprove(expected_version=1, expected_target_version=0),
        uuid.uuid4(),
        policy=r.policy,
        integrity=r.integrity,
    )
    error(
        "PROPOSAL_STALE",
        lambda: review.approve(
            r.db,
            r.user.id,
            second["proposal_id"],
            ProposalApprove(expected_version=1, expected_target_version=0),
            uuid.uuid4(),
            policy=r.policy,
            integrity=r.integrity,
        ),
    )
    assert count(r, Memory) == 1
    assert r.db.get(RevisionProposal, second["proposal_id"]).state == "stale"
    assert approved["memory_id"] is not None


def test_b33_revision_sequence_separate_effective_version(records):
    r = records
    first = manual(r)
    second, _ = review.create_candidate_revision(
        r.db,
        r.user.id,
        first["candidate_id"],
        RevisionCreate(
            expected_version=0,
            parent_revision_id=first["revision_id"],
            payload=payload("合成第二稿"),
        ),
        uuid.uuid4(),
        policy=r.policy,
        integrity=r.integrity,
    )
    candidate = r.db.get(MemoryCandidate, first["candidate_id"])
    assert candidate.version == 0 and candidate.revision_counter == 2
    assert r.db.get(ContentRevision, second["revision_id"]).ordinal == 2


def test_b36_controls_work_without_integrity_or_policy(records):
    r = records
    first = manual(r)
    submit(r, first)
    r.keys.keys.clear()
    r.policy.decisions.clear()
    rejected, _ = review.reject(
        r.db, r.user.id, first["proposal_id"], ProposalReject(expected_version=1), uuid.uuid4()
    )
    assert rejected["state"] == "rejected"
    error(
        "PROPOSAL_STATE_CONFLICT",
        lambda: review.withdraw(
            r.db, r.user.id, first["proposal_id"], VersionCommand(expected_version=2), uuid.uuid4()
        ),
    )


@pytest.mark.parametrize("kind", ["interview", "member", "family"])
@pytest.mark.parametrize("number", [0, 1])
def test_b49_b50_old_delete_protects_all_material(records, kind, number):
    r = records

    class Provider:
        provider_id = "mock"

        def extract(self, request):
            return MemoryExtractionResult(
                request_id=request.request_id,
                contract_version=request.contract_version,
                source_message_id=request.source_message_id,
                candidates=tuple(payload() for _ in range(number)),
            )

    extract(r, Provider())
    if kind == "interview":
        action = lambda: interview_service.delete_interview(
            r.db, user_id=r.user.id, interview_id=r.interview.id
        )
    elif kind == "member":
        action = lambda: member_service.delete_family_member(
            r.db, user_id=r.user.id, family_id=r.family.id, member_id=r.member.id
        )
    else:
        action = lambda: family_service.delete_family(
            r.db, user_id=r.user.id, family_id=r.family.id
        )
    error("RESOURCE_IN_USE", action)
    assert r.db.get(InterviewMessage, r.source.id) is not None
    assert count(r, ExtractionBatch) == 1 and count(r, MemoryCandidate) == number


@pytest.mark.parametrize("kind", ["interview", "member", "family"])
def test_b51_old_delete_without_refs_uses_db_cascade(records, kind):
    r = records
    if kind == "interview":
        interview_service.delete_interview(r.db, user_id=r.user.id, interview_id=r.interview.id)
    elif kind == "member":
        member_service.delete_family_member(
            r.db, user_id=r.user.id, family_id=r.family.id, member_id=r.member.id
        )
    else:
        family_service.delete_family(r.db, user_id=r.user.id, family_id=r.family.id)
    assert (
        r.db.scalar(
            select(func.count())
            .select_from(InterviewMessage)
            .where(InterviewMessage.id == r.source.id)
        )
        == 0
    )


@pytest.mark.parametrize(
    "sqlstate,pair,expected",
    [
        ("23503", ("memory_extraction_batches", "fk_mxb_session"), True),
        ("23503", ("memory_candidates", "fk_mc_member"), True),
        ("23503", ("unrelated", "fk_mxb_session"), False),
        ("23503", ("memory_extraction_batches", "unknown"), False),
        ("23502", ("memory_candidates", "fk_mc_member"), False),
        ("23505", ("memory_candidates", "fk_mc_member"), False),
    ],
)
def test_b54_pg_classification_is_simulated_only(sqlstate, pair, expected):
    db = Mock()
    diagnostic = SimpleNamespace(table_name=pair[0], constraint_name=pair[1])
    original = SimpleNamespace(sqlstate=sqlstate, diag=diagnostic)
    failure = IntegrityError("sensitive SQL", {}, original)
    if expected:
        error(
            "RESOURCE_IN_USE",
            lambda: interview_service._delete_with_reference_guard(
                db,
                has_references=lambda: False,
                delete=Mock(side_effect=failure),
                constraint_names=set(),
                reauthorize=lambda: None,
            ),
        )
    else:
        with pytest.raises(IntegrityError):
            interview_service._delete_with_reference_guard(
                db,
                has_references=lambda: False,
                delete=Mock(side_effect=failure),
                constraint_names=set(),
            )
    assert db.rollback.called
    assert pair in PROTECTED_DELETE_FK_MANIFEST if expected else True


def test_b57_unknown_reconciliation_is_read_only(records, monkeypatch):
    r = records
    monkeypatch.setattr(commands, "begin_memory", Mock(side_effect=AssertionError("not readonly")))
    error(
        "COMMAND_OUTCOME_UNKNOWN",
        lambda: review.command_status(r.db, r.user.id, r.member.id, "memory.extract", uuid.uuid4()),
    )
    assert count(r, CommandIdempotencyRecord) == 0


def test_b57_terminal_reconciliation_does_not_need_key(records):
    r = records
    key = uuid.uuid4()
    first = manual(r, key=key)
    r.keys.keys.clear()
    result, status = review.command_status(
        r.db, r.user.id, r.member.id, "memory.candidate.manual", key
    )
    assert status == 200 and result["candidate_id"] == str(first["candidate_id"])


@pytest.mark.parametrize(
    "path,method,expected",
    [
        ("/api/v1/family-members/id/memory-candidates/manual", "POST", True),
        ("/api/v1/families/id", "DELETE", True),
        ("/api/v1/families/id/members/id", "DELETE", True),
        ("/api/v1/sessions/id/agent-turns", "POST", False),
        ("/api/v1/auth/login", "POST", False),
        ("/api/v1/families/id", "GET", False),
    ],
)
def test_privacy_scope_is_narrow_pure_unit(path, method, expected):
    assert is_memory_path(path, method) is expected


def test_privacy_serializer_omits_exception_detail_no_http(caplog):
    response = memory_exception_response(RuntimeError("synthetic-password raw SQL payload"))
    assert response.status_code == 500
    assert b"synthetic-password" not in response.body
    assert "raw SQL" not in caplog.text


@pytest.mark.parametrize("committed", [False, True])
def test_b19_uncertain_commit_uses_read_only_reconciliation(records, monkeypatch, committed):
    r = records
    key = uuid.uuid4()
    original_commit = r.db.commit

    def uncertain_commit():
        if committed:
            original_commit()
        raise RuntimeError("synthetic private SQL failure")

    monkeypatch.setattr(r.db, "commit", uncertain_commit)
    failure = error("COMMAND_OUTCOME_UNKNOWN", lambda: manual(r, key=key))
    assert failure.details["outcome"] == "unknown"
    assert failure.details["operation"] == "memory.candidate.manual"
    assert failure.details["idempotency_key"] == str(key)
    uuid.UUID(failure.details["command_id"])
    assert count(r, MemoryCandidate) == int(committed)
    monkeypatch.setattr(r.db, "commit", Mock(side_effect=AssertionError("query cannot commit")))
    monkeypatch.setattr(
        commands, "begin_memory", Mock(side_effect=AssertionError("query cannot begin"))
    )
    monkeypatch.setattr(
        workflow_crud, "source_content", Mock(side_effect=AssertionError("query cannot read body"))
    )
    if committed:
        response, status = review.command_status(
            r.db, r.user.id, r.member.id, "memory.candidate.manual", key
        )
        assert status == 200 and response["command_id"] == uuid.UUID(failure.details["command_id"])
    else:
        queried = error(
            "COMMAND_OUTCOME_UNKNOWN",
            lambda: review.command_status(
                r.db, r.user.id, r.member.id, "memory.candidate.manual", key
            ),
        )
        assert queried.details["outcome"] == "unknown"
    assert count(r, MemoryCandidate) == int(committed)


def test_b19_rollback_failure_keeps_unknown_context_without_database():
    record = SimpleNamespace(
        id=uuid.uuid4(), operation="memory.extract", idempotency_key=uuid.uuid4()
    )
    db = SimpleNamespace(
        commit=Mock(side_effect=RuntimeError("synthetic commit failure")),
        rollback=Mock(side_effect=RuntimeError("synthetic rollback failure")),
    )
    failure = error("COMMAND_OUTCOME_UNKNOWN", lambda: review.commit(db, record))
    assert failure.details == {
        "outcome": "unknown",
        "operation": record.operation,
        "command_id": str(record.id),
        "idempotency_key": str(record.idempotency_key),
    }
    db.rollback.assert_called_once()


def test_b17_unknown_serializer_only_typed_context_no_http(caplog):
    command_id, key = uuid.uuid4(), uuid.uuid4()
    failure = AppException(
        "synthetic secret SQL parameters",
        code="COMMAND_OUTCOME_UNKNOWN",
        status_code=503,
        details={
            "operation": "memory.extract",
            "command_id": command_id,
            "idempotency_key": str(key),
            "payload": "synthetic sensitive body",
        },
    )
    response = memory_exception_response(failure)
    assert response.status_code == 503
    assert json.loads(response.body)["error"]["details"] == {
        "outcome": "unknown",
        "operation": "memory.extract",
        "command_id": str(command_id),
        "idempotency_key": str(key),
    }
    assert b"sensitive" not in response.body and "SQL parameters" not in caplog.text


def test_b35_approval_flush_failure_rolls_back_all_promotion(records, monkeypatch):
    r = records
    created = manual(r)
    submit(r, created)
    original_flush = r.db.flush

    def failed_flush(*args, **kwargs):
        if any(
            isinstance(row, ContentRevision) and row.author_mode == "promotion" for row in r.db.new
        ):
            raise RuntimeError("synthetic private database error")
        return original_flush(*args, **kwargs)

    monkeypatch.setattr(r.db, "flush", failed_flush)
    error(
        "MEMORY_STORAGE_UNAVAILABLE",
        lambda: review.approve(
            r.db,
            r.user.id,
            created["proposal_id"],
            ProposalApprove(expected_version=1, expected_target_version=0),
            uuid.uuid4(),
            policy=r.policy,
            integrity=r.integrity,
        ),
    )
    assert count(r, Memory) == 0 and count(r, ContentRevision) == 1
    candidate = r.db.get(MemoryCandidate, created["candidate_id"])
    proposal = r.db.get(RevisionProposal, created["proposal_id"])
    assert candidate.version == 0 and candidate.promoted_memory_id is None
    assert proposal.state == "submitted" and proposal.version == 1
    assert proposal.result_memory_id is None and proposal.result_memory_revision_id is None
    assert count(r, CommandIdempotencyRecord) == 2
    assert r.db.get(InterviewMessage, r.source.id).content == " 合成：小时候常在河边坐着。 "


def test_b18_partial_extraction_failure_has_no_orphan_revision(records, monkeypatch):
    r = records
    original_add = workflow_crud.add_flush
    seen = []

    def failed_add(db, row):
        if isinstance(row, MemoryCandidate):
            seen.append(row.id)
            if len(seen) == 2:
                raise RuntimeError("synthetic private persistence failure")
        return original_add(db, row)

    class Provider:
        provider_id = "mock"

        def extract(self, request):
            return MemoryExtractionResult(
                request_id=request.request_id,
                contract_version=request.contract_version,
                source_message_id=request.source_message_id,
                candidates=(payload(), payload()),
            )

    monkeypatch.setattr(workflow_crud, "add_flush", failed_add)
    error("MEMORY_STORAGE_UNAVAILABLE", lambda: extract(r, Provider()))
    assert count(r, MemoryCandidate) == count(r, ContentRevision) == count(r, RevisionProposal) == 0
    batch = r.db.scalar(select(ExtractionBatch))
    assert batch.state == "failed" and batch.failure_code == "PERSISTENCE_FAILED"
    assert count(r, CommandIdempotencyRecord) == 1


@pytest.mark.parametrize("kind", ["interview", "member", "family"])
def test_b53_current_owner_predicate_prevents_delete_after_precheck(records, monkeypatch, kind):
    r = records
    original = workflow_crud.has_workflow_references

    def changed_owner(db, **scope):
        found = original(db, **scope)
        db.execute(update(Family).where(Family.id == r.family.id).values(owner_id=r.other.id))
        return found

    monkeypatch.setattr(workflow_crud, "has_workflow_references", changed_owner)
    if kind == "interview":
        action = lambda: interview_service.delete_interview(
            r.db, user_id=r.user.id, interview_id=r.interview.id
        )
    elif kind == "member":
        action = lambda: member_service.delete_family_member(
            r.db, user_id=r.user.id, family_id=r.family.id, member_id=r.member.id
        )
    else:
        action = lambda: family_service.delete_family(
            r.db, user_id=r.user.id, family_id=r.family.id
        )
    error("NOT_FOUND", action)
    assert count(r, InterviewMessage) == count(r, InterviewSession) == count(r, Interview) == 1
    assert r.db.scalar(select(Family.owner_id).where(Family.id == r.family.id)) == r.user.id


@pytest.mark.parametrize("missing", ["policy", "integrity"])
def test_b06_default_capabilities_before_source_body(records, monkeypatch, missing):
    r = records
    monkeypatch.setattr(
        workflow_crud,
        "source_content",
        Mock(side_effect=AssertionError("source body read before gate")),
    )
    provider = SimpleNamespace(
        extract=Mock(side_effect=AssertionError("provider called before gate"))
    )
    code = (
        "MEMORY_PROCESSING_UNAVAILABLE" if missing == "policy" else "MEMORY_INTEGRITY_UNAVAILABLE"
    )
    error(
        code,
        lambda: extraction.start(
            r.db,
            r.user.id,
            r.session.id,
            ExtractionCreate(source_message_id=r.source.id),
            uuid.uuid4(),
            policy=None if missing == "policy" else r.policy,
            integrity=None if missing == "integrity" else r.integrity,
            client=provider,
        ),
    )
    assert count(r, ExtractionBatch) == count(r, CommandIdempotencyRecord) == 0


@pytest.mark.parametrize("clear", [False, True])
def test_b31_candidate_promoted_pointer_write_once_when_expired(records, clear):
    r = records
    first = manual(r)
    promoted = approve(r, first)
    second = manual(r)
    other = approve(r, second)
    candidate = r.db.get(MemoryCandidate, first["candidate_id"])
    r.db.expire(candidate, ["promoted_memory_id"])
    candidate.promoted_memory_id = None if clear else other["memory_id"]
    with pytest.raises(ValueError, match="promotion is immutable"):
        r.db.flush()
    r.db.rollback()
    assert (
        r.db.get(MemoryCandidate, first["candidate_id"]).promoted_memory_id == promoted["memory_id"]
    )


def test_b27_batch_terminal_cannot_reopen_when_expired(records):
    r = records
    completed = extract(r)
    batch = r.db.get(ExtractionBatch, completed["batch_id"])
    r.db.expire(batch, ["state"])
    batch.state, batch.candidate_count, batch.finished_at = "pending", None, None
    with pytest.raises(ValueError, match="terminal state is immutable"):
        r.db.flush()
    r.db.rollback()
    assert r.db.get(ExtractionBatch, completed["batch_id"]).state == "completed"


def test_b27_proposal_purge_can_clear_digest_but_cannot_replace_it(records):
    r = records
    created = manual(r)
    proposal = r.db.get(RevisionProposal, created["proposal_id"])
    r.db.expire(proposal)
    proposal.state, proposal.payload_digest = "purged", b"z" * 32
    with pytest.raises(ValueError, match="digest is immutable"):
        r.db.flush()
    r.db.rollback()
    proposal = r.db.get(RevisionProposal, created["proposal_id"])
    proposal.state = "purged"
    proposal.payload_digest = proposal.digest_scheme = proposal.digest_key_id = None
    r.db.commit()
    r.db.expire(proposal)
    proposal.state = "draft"
    with pytest.raises(ValueError, match="terminal state cannot be reopened"):
        r.db.flush()
    r.db.rollback()
    assert r.db.get(RevisionProposal, created["proposal_id"]).state == "purged"


@pytest.mark.parametrize("kind", ["interview", "member", "family"])
def test_b52_stale_precheck_real_sqlite_fk_preserves_source(records, monkeypatch, kind):
    """A stale metadata probe exercises real in-memory FK fallback, not a PG race."""
    r = records
    created = manual(r)
    original = workflow_crud.has_workflow_references
    probes, diagnostics = [], []

    def stale_first_probe(db, **scope):
        probes.append(scope)
        return False if len(probes) == 1 else original(db, **scope)

    @event.listens_for(r.engine, "handle_error")
    def capture_error(context):
        diagnostics.append(getattr(context.original_exception, "sqlite_errorcode", None))

    monkeypatch.setattr(workflow_crud, "has_workflow_references", stale_first_probe)
    if kind == "interview":
        action = lambda: interview_service.delete_interview(
            r.db, user_id=r.user.id, interview_id=r.interview.id
        )
    elif kind == "member":
        action = lambda: member_service.delete_family_member(
            r.db, user_id=r.user.id, family_id=r.family.id, member_id=r.member.id
        )
    else:
        action = lambda: family_service.delete_family(
            r.db, user_id=r.user.id, family_id=r.family.id
        )
    error("RESOURCE_IN_USE", action)
    assert len(probes) == 2 and diagnostics
    assert diagnostics[0] in (787, 1811)  # FOREIGNKEY or RESTRICT-trigger extended SQLite codes.
    r.db.expire_all()
    assert r.db.get(InterviewMessage, r.source.id).content == " 合成：小时候常在河边坐着。 "
    assert r.db.get(MemoryCandidate, created["candidate_id"]) is not None
    assert count(r, RevisionProposal) == count(r, ContentRevision) == 1


@pytest.mark.parametrize("phase", ["flush", "commit"])
def test_b54_unknown_fk_and_sqlite_trigger_are_not_reference_conflicts(phase):
    import sqlite3

    original = sqlite3.IntegrityError("synthetic unrelated trigger")
    original.sqlite_errorcode = sqlite3.SQLITE_CONSTRAINT_TRIGGER
    failure = IntegrityError("synthetic private SQL", {}, original)
    db = Mock()
    delete = Mock(return_value=True)
    if phase == "flush":
        delete.side_effect = failure
    else:
        db.commit.side_effect = failure
    with pytest.raises(IntegrityError):
        interview_service._delete_with_reference_guard(
            db, has_references=lambda: False, delete=delete, constraint_names=set()
        )
    assert db.rollback.called


def test_b57_processing_lookup_has_no_body_or_autoflush(records, monkeypatch):
    r = records
    key, pending = uuid.uuid4(), []

    class Provider:
        provider_id = "mock"

        def extract(self, request):
            monkeypatch.setattr(
                r.db, "flush", Mock(side_effect=AssertionError("query cannot flush"))
            )
            response, status = review.command_status(
                r.db, r.user.id, r.member.id, "memory.extract", key
            )
            assert status == 202 and response["resource_id"] == request.request_id
            pending.append(response)
            return r.client.extract(request)

    # Patch only around the read-only lookup; finalize requires normal transactional flush.
    original_flush = r.db.flush

    class RestoredProvider(Provider):
        def extract(self, request):
            try:
                return super().extract(request)
            finally:
                monkeypatch.setattr(r.db, "flush", original_flush)

    extract(r, RestoredProvider(), key)
    assert len(pending) == 1 and count(r, MemoryCandidate) == 1


@pytest.mark.parametrize(
    "violation",
    [
        "revision_none",
        "revision_both",
        "proposal_none",
        "proposal_both",
        "input_wrong_candidate",
        "current_pair",
        "current_wrong_proof",
        "result_pair",
        "revision_duplicate_ordinal",
    ],
)
def test_b34_real_sqlite_checks_and_composite_fks(records, violation):
    """Core SQL deliberately bypasses ORM protection to verify actual SQLite constraints."""
    r = records
    first, second = manual(r), manual(r)
    first_approval, second_approval = approve(r, first), approve(r, second)
    statements = {
        "revision_none": update(ContentRevision)
        .where(ContentRevision.id == first["revision_id"])
        .values(candidate_id=None),
        "revision_both": update(ContentRevision)
        .where(ContentRevision.id == first["revision_id"])
        .values(memory_id=first_approval["memory_id"]),
        "proposal_none": update(RevisionProposal)
        .where(RevisionProposal.id == first["proposal_id"])
        .values(candidate_id=None),
        "proposal_both": update(RevisionProposal)
        .where(RevisionProposal.id == first["proposal_id"])
        .values(memory_id=first_approval["memory_id"]),
        "input_wrong_candidate": update(RevisionProposal)
        .where(RevisionProposal.id == first["proposal_id"])
        .values(input_revision_id=second["revision_id"]),
        "current_pair": update(Memory)
        .where(Memory.id == first_approval["memory_id"])
        .values(current_revision_id=None),
        "current_wrong_proof": update(Memory)
        .where(Memory.id == first_approval["memory_id"])
        .values(
            current_revision_id=second_approval["memory_revision_id"],
            current_approval_proposal_id=second["proposal_id"],
        ),
        "result_pair": update(RevisionProposal)
        .where(RevisionProposal.id == first["proposal_id"])
        .values(result_memory_revision_id=None),
        "revision_duplicate_ordinal": update(ContentRevision)
        .where(ContentRevision.id == first["revision_id"])
        .values(candidate_id=second["candidate_id"]),
    }
    with pytest.raises(IntegrityError):
        r.db.execute(statements[violation].execution_options(synchronize_session=False))
        r.db.flush()
    r.db.rollback()
    assert count(r, Memory) == count(r, MemoryCandidate) == count(r, RevisionProposal) == 2
    assert (
        r.db.get(Memory, first_approval["memory_id"]).current_approval_proposal_id
        == first["proposal_id"]
    )


def test_b17_b57_typed_metadata_results_preserve_replay_shape(records):
    r = records
    extracted = extract(r)
    assert ExtractionCommandResult.model_validate(extracted).model_dump(
        mode="json", exclude_unset=True
    ) == json.loads(json.dumps(extracted, default=str))
    batch = extraction.get_batch(r.db, r.user.id, extracted["batch_id"])
    ExtractionBatchRead.model_validate(batch)
    key = uuid.uuid4()
    created = manual(r, key=key)
    assert RevisionCreated.model_validate(created).model_dump(
        mode="json", exclude_unset=True
    ) == json.loads(json.dumps(created, default=str))
    CandidateRead.model_validate(review.get_candidate(r.db, r.user.id, created["candidate_id"]))
    items, total = review.list_revisions(r.db, r.user.id, created["candidate_id"])
    RevisionList.model_validate({"items": items, "total": total, "page": 1, "page_size": 20})
    RevisionContent.model_validate(
        review.get_revision_content(
            r.db, r.user.id, created["revision_id"], policy=r.policy, integrity=r.integrity
        )
    )
    approved = approve(r, created)
    ProposalRead.model_validate(review.get_proposal(r.db, r.user.id, created["proposal_id"]))
    ProposalCommandResult.model_validate(approved)
    lookup, status = review.command_status(
        r.db, r.user.id, r.member.id, "memory.candidate.manual", key
    )
    assert status == 200
    assert TypeAdapter(MemoryCommandResult).validate_python(lookup).model_dump(
        mode="json", exclude_unset=True
    ) == json.loads(json.dumps(lookup, default=str))
    with pytest.raises(ValidationError):
        TypeAdapter(MemoryCommandResult).validate_python(
            {**lookup, "content": "synthetic private body"}
        )


def test_b48_all_workflow_routes_declare_output_contract_without_importing_asgi():
    import ast

    path = Path(__file__).resolve().parents[1] / "app/api/v1/memory_workflow.py"
    count_routes = 0
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.FunctionDef):
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr in {"get", "post"}
                ):
                    count_routes += 1
                    assert "response_model" in {keyword.arg for keyword in decorator.keywords}
    assert count_routes == 18


def test_b43_b44_memoir_typed_content_and_creation_metadata(records):
    r = records
    created = manual(r)
    approved = approve(r, created)
    result, status = memoir_service.create(
        r.db,
        r.user.id,
        r.member.id,
        MemoirCreate(
            title=" 合成回忆录 ",
            sections=(
                {
                    "memory_id": approved["memory_id"],
                    "memory_revision_id": approved["memory_revision_id"],
                    "approval_proposal_id": created["proposal_id"],
                },
            ),
        ),
        uuid.uuid4(),
        policy=r.policy,
        integrity=r.integrity,
    )
    assert status == 201
    assert MemoirCreated.model_validate(result).model_dump(
        mode="json", exclude_unset=True
    ) == json.loads(json.dumps(result, default=str))
    content = memoir_service.content(
        r.db, r.user.id, result["memoir_id"], policy=r.policy, integrity=r.integrity
    )
    parsed = MemoirContent.model_validate(content)
    assert parsed.title == " 合成回忆录 " and parsed.sections[0].content == payload().content
    section = memoir_service.section_content(
        r.db,
        r.user.id,
        result["memoir_id"],
        result["section_ids"][0],
        policy=r.policy,
        integrity=r.integrity,
    )
    assert (
        MemoirSectionContent.model_validate(section).approval_proposal_id == created["proposal_id"]
    )


# Remediation #1: these are Service/SQLite probes, never PostgreSQL lock evidence.
@pytest.mark.parametrize("identity", ["missing", None, "unknown", "", 1, True])
def test_b_ir01_unknown_or_missing_provider_before_body_and_batch(records, monkeypatch, identity):
    r = records
    provider = SimpleNamespace(extract=Mock())
    if identity != "missing":
        provider.provider_id = identity
    body = Mock(wraps=workflow_crud.source_content)
    monkeypatch.setattr(workflow_crud, "source_content", body)
    failure = error("MEMORY_PROCESSING_UNAVAILABLE", lambda: extract(r, provider))
    assert failure.status_code == 503
    provider.extract.assert_not_called()
    body.assert_not_called()
    assert count(r, ExtractionBatch) == count(r, CommandIdempotencyRecord) == 0
    assert count(r, MemoryCandidate) == 0


def test_b_ir01_unavailable_default_keeps_source_unread(records, monkeypatch):
    r = records
    factory = Mock(return_value=UnavailableMemoryClient())
    body = Mock(wraps=workflow_crud.source_content)
    monkeypatch.setattr(extraction, "get_memory_client", factory)
    monkeypatch.setattr(workflow_crud, "source_content", body)
    error(
        "MEMORY_PROCESSING_UNAVAILABLE",
        lambda: extraction.start(
            r.db,
            r.user.id,
            r.session.id,
            ExtractionCreate(source_message_id=r.source.id),
            uuid.uuid4(),
            policy=r.policy,
            integrity=r.integrity,
        ),
    )
    factory.assert_called_once_with()
    body.assert_not_called()
    assert count(r, ExtractionBatch) == 0


def test_b_ir01_owner_and_capabilities_precede_provider_resolution(records, monkeypatch):
    r = records
    factory = Mock(side_effect=AssertionError("adapter must not be resolved"))
    monkeypatch.setattr(extraction, "get_memory_client", factory)
    error(
        "NOT_FOUND",
        lambda: extraction.start(
            r.db,
            r.other.id,
            r.session.id,
            ExtractionCreate(source_message_id=r.source.id),
            uuid.uuid4(),
            policy=r.policy,
            integrity=r.integrity,
        ),
    )
    error(
        "MEMORY_PROCESSING_UNAVAILABLE",
        lambda: extraction.start(
            r.db,
            r.user.id,
            r.session.id,
            ExtractionCreate(source_message_id=r.source.id),
            uuid.uuid4(),
            integrity=r.integrity,
        ),
    )
    factory.assert_not_called()
    assert count(r, ExtractionBatch) == 0


def test_b_ir01_same_validated_mock_object_and_batch_identity(records, monkeypatch):
    r = records
    requests = []

    class CountedMock(DeterministicMockMemoryClient):
        def extract(self, request):
            assert not r.db.in_transaction()
            requests.append(request)
            return super().extract(request).validate_binding(request)

    provider = CountedMock()
    factory = Mock(return_value=provider)
    monkeypatch.setattr(extraction, "get_memory_client", factory)
    result, status = extraction.start(
        r.db,
        r.user.id,
        r.session.id,
        ExtractionCreate(source_message_id=r.source.id),
        uuid.uuid4(),
        policy=r.policy,
        integrity=r.integrity,
    )
    assert status == 201 and len(requests) == 1
    factory.assert_called_once_with()
    request = requests[0]
    batch = r.db.get(ExtractionBatch, result["batch_id"])
    assert batch.provider_id == provider.provider_id == "mock"
    assert batch.id == request.request_id and batch.source_message_id == request.source_message_id
    assert request.source_text == r.source.content


@pytest.mark.parametrize("state", ["completed", "pending"])
def test_b_ir01_replay_does_not_resolve_or_inspect_provider(records, monkeypatch, state):
    r = records
    key = uuid.uuid4()
    if state == "completed":
        expected = extract(r, key=key)
    else:
        request, provider, replay = extraction._prepare(
            r.db,
            r.user.id,
            r.session.id,
            ExtractionCreate(source_message_id=r.source.id),
            key,
            policy=r.policy,
            integrity=r.integrity,
            client=r.client,
        )
        assert replay is None and provider is r.client
        expected = {"batch_id": request.request_id}
    factory = Mock(side_effect=AssertionError("replay cannot resolve provider"))
    monkeypatch.setattr(extraction, "get_memory_client", factory)
    body = Mock(side_effect=AssertionError("replay cannot query source body"))
    monkeypatch.setattr(workflow_crud, "source_content", body)

    class PoisonProvider:
        @property
        def provider_id(self):
            pytest.fail("replay cannot inspect adapter identity")

    for provider in (None, PoisonProvider()):
        replay, status = extraction.start(
            r.db,
            r.user.id,
            r.session.id,
            ExtractionCreate(source_message_id=r.source.id),
            key,
            client=provider,
        )
        assert status == (200 if state == "completed" else 202)
        assert str(replay["batch_id"]) == str(expected["batch_id"])
    factory.assert_not_called()
    body.assert_not_called()
    assert count(r, ExtractionBatch) == 1


def _memoir_data(approvals):
    return MemoirCreate(
        title="合成锁测试",
        sections=tuple(
            {
                "memory_id": item["memory_id"],
                "memory_revision_id": item["memory_revision_id"],
                "approval_proposal_id": item["proposal_id"],
            }
            for item in approvals
        ),
    )


def _create_memoir(r, data, key=None):
    return memoir_service.create(
        r.db,
        r.user.id,
        r.member.id,
        data,
        key or uuid.uuid4(),
        policy=r.policy,
        integrity=r.integrity,
    )


def test_b_ir02_lock_order_and_gate_before_body(records, monkeypatch):
    from sqlalchemy.dialects import postgresql

    r = records
    approvals = [approve(r, manual(r)) for _ in range(2)]
    data = _memoir_data(approvals[::-1])
    trace, sql_locks = [], []
    original_command, original_memory, original_owned = (
        review._command,
        review.owned_memory,
        review.owned,
    )
    original_proof, original_body = workflow_crud.proposal_proof, workflow_crud.revision_body

    def command(*args, **kwargs):
        trace.append(("command", None))
        return original_command(*args, **kwargs)

    def memory(db, user_id, record_id, **kwargs):
        if kwargs.get("lock"):
            trace.append(("memory", record_id))
        return original_memory(db, user_id, record_id, **kwargs)

    def owned(db, model, user_id, record_id, **kwargs):
        if kwargs.get("lock"):
            trace.append(("proposal" if model is RevisionProposal else "revision", record_id))
        return original_owned(db, model, user_id, record_id, **kwargs)

    expected = (
        [("command", None)]
        + [("memory", x) for x in sorted((a["memory_id"] for a in approvals), key=str)]
        + [("proposal", x) for x in sorted((a["proposal_id"] for a in approvals), key=str)]
        + [("revision", x) for x in sorted((a["memory_revision_id"] for a in approvals), key=str)]
    )

    def proof(*args):
        assert trace == expected
        return original_proof(*args)

    def body(*args):
        assert trace == expected
        return original_body(*args)

    def capture_sql(state):
        statement = state.statement
        if getattr(statement, "_for_update_arg", None) is not None:
            compiled = str(statement.compile(dialect=postgresql.dialect()))
            if "command_idempotency_records" in compiled:
                assert "FOR UPDATE" in compiled
                return
            sql_locks.append(compiled)
            assert "FOR UPDATE OF" in compiled
            assert "memory_content_revisions.payload" not in compiled

    monkeypatch.setattr(review, "_command", command)
    monkeypatch.setattr(review, "owned_memory", memory)
    monkeypatch.setattr(review, "owned", owned)
    monkeypatch.setattr(workflow_crud, "proposal_proof", proof)
    monkeypatch.setattr(workflow_crud, "revision_body", body)
    event.listen(r.db, "do_orm_execute", capture_sql)
    try:
        result, status = _create_memoir(r, data)
    finally:
        event.remove(r.db, "do_orm_execute", capture_sql)
    assert trace == expected and len(sql_locks) == 6
    assert status == 201 and len(result["section_ids"]) == 2
    sections = r.db.scalars(select(MemoirSection).order_by(MemoirSection.position)).all()
    assert [s.memory_id for s in sections] == [a["memory_id"] for a in approvals[::-1]]
    assert all(s.content == payload().content for s in sections)


def test_b_ir02_duplicate_memory_and_repeated_proof_refs_fail_closed(records, monkeypatch):
    r = records
    approvals = [approve(r, manual(r)) for _ in range(2)]
    with pytest.raises(ValidationError):
        _memoir_data([approvals[0], approvals[0]])
    repeated = dict(approvals[0], memory_id=approvals[1]["memory_id"])
    data = _memoir_data([approvals[0], repeated])
    locks = []
    original = review.owned

    def locked(db, model, user_id, record_id, **kwargs):
        if kwargs.get("lock"):
            locks.append((model, record_id))
        return original(db, model, user_id, record_id, **kwargs)

    monkeypatch.setattr(review, "owned", locked)
    error("INVALID_APPROVED_REVISION", lambda: _create_memoir(r, data))
    assert locks == [
        (RevisionProposal, approvals[0]["proposal_id"]),
        (ContentRevision, approvals[0]["memory_revision_id"]),
    ]
    assert count(r, Memoir) == count(r, MemoirSection) == 0


@pytest.mark.parametrize("change", ["proof", "body", "epoch", "digest"])
def test_b_ir02_lock_time_invalidation_no_snapshot(records, monkeypatch, change):
    r = records
    approved = approve(r, manual(r))
    before_commands = count(r, CommandIdempotencyRecord)
    original = review.owned
    changed = False
    body = Mock(wraps=workflow_crud.revision_body)

    def lock_and_invalidate(db, model, user_id, record_id, **kwargs):
        nonlocal changed
        record = original(db, model, user_id, record_id, **kwargs)
        if model is ContentRevision and kwargs.get("lock") and not changed:
            changed = True
            if change == "proof":
                db.execute(
                    update(RevisionProposal)
                    .where(RevisionProposal.id == approved["proposal_id"])
                    .values(
                        state="purged", payload_digest=None, digest_scheme=None, digest_key_id=None
                    )
                )
            elif change == "body":
                db.execute(
                    update(ContentRevision)
                    .where(ContentRevision.id == approved["memory_revision_id"])
                    .values(
                        body_state="purged",
                        payload=None,
                        content_digest=None,
                        digest_scheme=None,
                        digest_key_id=None,
                    )
                )
            elif change == "digest":
                db.execute(
                    update(ContentRevision)
                    .where(ContentRevision.id == approved["memory_revision_id"])
                    .values(content_digest=b"z" * 32)
                )
            else:
                stamp = r.policy.decisions[r.source.id]
                r.policy.decisions[r.source.id] = stamp.model_copy(
                    update={
                        "source_generation": stamp.source_generation + 1,
                    }
                )
        return record

    monkeypatch.setattr(review, "owned", lock_and_invalidate)
    monkeypatch.setattr(workflow_crud, "revision_body", body)
    error(
        {
            "proof": "INVALID_APPROVED_REVISION",
            "body": "CONTENT_RESTRICTED",
            "epoch": "CONTENT_RESTRICTED",
            "digest": "CONTENT_RESTRICTED",
        }[change],
        lambda: _create_memoir(r, _memoir_data([approved])),
    )
    assert changed
    if change != "digest":
        body.assert_not_called()
    assert count(r, Memoir) == count(r, MemoirSection) == 0
    assert count(r, CommandIdempotencyRecord) == before_commands
    assert r.db.get(RevisionProposal, approved["proposal_id"]).state == "approved"
    assert r.db.get(ContentRevision, approved["memory_revision_id"]).body_state == "present"


def test_b_ir02_section_flush_failure_rolls_back_parent_and_all_sections(records):
    r = records
    data = _memoir_data([approve(r, manual(r)) for _ in range(2)])
    before_commands = count(r, CommandIdempotencyRecord)
    seen = []

    def fail_second(_mapper, _connection, target):
        seen.append(target.id)
        if len(seen) == 2:
            raise RuntimeError("synthetic section persistence failure")

    event.listen(MemoirSection, "before_insert", fail_second)
    try:
        error("MEMORY_STORAGE_UNAVAILABLE", lambda: _create_memoir(r, data))
    finally:
        event.remove(MemoirSection, "before_insert", fail_second)
    assert len(seen) == 2
    assert count(r, Memoir) == count(r, MemoirSection) == 0
    assert count(r, CommandIdempotencyRecord) == before_commands


# Supplemental contract V1.0: synthetic branches; no production Consent claims.
def _supp_source(r, scope):
    owner = r.other if scope == "other_owner" else r.user
    if scope in {"other_family", "other_owner"}:
        family = Family(owner_id=owner.id, name="Synthetic alternate archive")
        r.db.add(family)
        r.db.flush()
    else:
        family = r.family
    if scope == "other_session":
        member = r.member
    else:
        member = FamilyMember(family_id=family.id, name="Synthetic alternate subject")
        r.db.add(member)
        r.db.flush()
    interview = Interview(family_member_id=member.id, title="Synthetic alternate interview")
    r.db.add(interview)
    r.db.flush()
    session = InterviewSession(interview_id=interview.id, status="completed")
    r.db.add(session)
    r.db.flush()
    source = InterviewMessage(
        session_id=session.id, role="user", source="text", sequence=1, content="Synthetic alternate"
    )
    r.db.add(source)
    r.db.commit()
    return source


@pytest.mark.parametrize("scope", ["other_session", "other_member", "other_family", "other_owner"])
def test_supp_b03_extraction_wrong_subject_before_body(records, monkeypatch, scope):
    r = records
    other = _supp_source(r, scope)
    body = Mock(side_effect=AssertionError("Wrong subject cannot read source"))
    provider = SimpleNamespace(provider_id="mock", extract=Mock())
    monkeypatch.setattr(workflow_crud, "source_content", body)
    failure = error(
        "NOT_FOUND",
        lambda: extraction.start(
            r.db,
            r.user.id,
            r.session.id,
            ExtractionCreate(source_message_id=other.id),
            uuid.uuid4(),
            policy=r.policy,
            integrity=r.integrity,
            client=provider,
        ),
    )
    assert failure.status_code == 404
    body.assert_not_called()
    provider.extract.assert_not_called()
    assert count(r, ExtractionBatch) == count(r, MemoryCandidate) == 0


@pytest.mark.parametrize(
    "role,source", [("assistant", "ai_generated"), ("system", "text"), ("user", "audio_transcript")]
)
def test_supp_b04_ai_source_categories_rejected_before_body(records, monkeypatch, role, source):
    r = records
    r.source.role, r.source.source = role, source
    r.db.commit()
    body = Mock(side_effect=AssertionError("Invalid category cannot read source"))
    monkeypatch.setattr(workflow_crud, "source_content", body)
    provider = SimpleNamespace(provider_id="mock", extract=Mock())
    failure = error("INVALID_SOURCE", lambda: extract(r, provider))
    assert failure.status_code == 422
    body.assert_not_called()
    provider.extract.assert_not_called()
    assert count(r, ExtractionBatch) == 0


@pytest.mark.parametrize("state", ["failed", "discarded", "cancelled"])
def test_supp_b12_terminal_replay_never_calls_provider(records, monkeypatch, state):
    r = records
    key = uuid.uuid4()

    class Provider:
        provider_id = "mock"

        def extract(self, request):
            if state == "failed":
                raise TimeoutError("Synthetic timeout")
            if state == "cancelled":
                extraction.cancel_batch(
                    r.db,
                    r.user.id,
                    request.request_id,
                    VersionCommand(expected_version=0),
                    uuid.uuid4(),
                )
            else:
                old = r.policy.decisions[r.source.id]
                r.policy.decisions[r.source.id] = old.model_copy(
                    update={"source_generation": old.source_generation + 1}
                )
            return r.client.extract(request)

    if state == "failed":
        error("AI_PROVIDER_TIMEOUT", lambda: extract(r, Provider(), key))
    else:
        assert extract(r, Provider(), key)["state"] == state
    before = (count(r, ExtractionBatch), count(r, MemoryCandidate), count(r, ContentRevision))
    forbidden = SimpleNamespace(extract=Mock(side_effect=AssertionError("Replay cannot generate")))
    monkeypatch.setattr(
        workflow_crud, "source_content", Mock(side_effect=AssertionError("Replay cannot read body"))
    )
    result, status = extraction.start(
        r.db,
        r.user.id,
        r.session.id,
        ExtractionCreate(source_message_id=r.source.id),
        key,
        policy=r.policy,
        integrity=r.integrity,
        client=forbidden,
    )
    assert result["state"] == state
    assert status == {"failed": 503, "discarded": 409, "cancelled": 200}[state]
    forbidden.extract.assert_not_called()
    assert before == (
        count(r, ExtractionBatch),
        count(r, MemoryCandidate),
        count(r, ContentRevision),
    )


def test_supp_b13_rerun_preserves_manual_revision_and_approved_memory(records):
    r = records
    initial = extract(r)
    cid = initial["candidate_ids"][0]
    candidate = review.get_candidate(r.db, r.user.id, cid)
    edited, _ = review.create_candidate_revision(
        r.db,
        r.user.id,
        cid,
        RevisionCreate(
            expected_version=0,
            parent_revision_id=candidate["revision_ids"][0],
            payload=payload("Synthetic corrected draft"),
        ),
        uuid.uuid4(),
        policy=r.policy,
        integrity=r.integrity,
    )
    approved = approve(r, {**edited, "candidate_id": cid})
    snapshots = {
        row.id: (row.payload.copy(), row.content_digest, row.ordinal)
        for row in r.db.scalars(select(ContentRevision))
    }
    current = r.db.get(Memory, approved["memory_id"]).current_revision_id
    again = extract(r)
    assert again["batch_id"] != initial["batch_id"] and again["candidate_ids"] != [cid]
    for rid, value in snapshots.items():
        row = r.db.get(ContentRevision, rid)
        assert (row.payload, row.content_digest, row.ordinal) == value
    assert r.db.get(Memory, approved["memory_id"]).current_revision_id == current
    assert count(r, Memory) == 1


def test_supp_b14_changed_source_and_revision_version_conflict(records):
    r = records
    second = InterviewMessage(
        session_id=r.session.id, role="user", source="text", sequence=2, content="Second synthetic"
    )
    r.db.add(second)
    r.db.commit()
    key = uuid.uuid4()
    extract(r, key=key)
    error(
        "IDEMPOTENCY_CONFLICT",
        lambda: extraction.start(
            r.db,
            r.user.id,
            r.session.id,
            ExtractionCreate(source_message_id=second.id),
            key,
            policy=r.policy,
            integrity=r.integrity,
            client=r.client,
        ),
    )
    first = manual(r)
    revision_key = uuid.uuid4()
    data = RevisionCreate(
        expected_version=0, parent_revision_id=first["revision_id"], payload=payload()
    )
    review.create_candidate_revision(
        r.db,
        r.user.id,
        first["candidate_id"],
        data,
        revision_key,
        policy=r.policy,
        integrity=r.integrity,
    )
    before = count(r, ContentRevision)
    error(
        "IDEMPOTENCY_CONFLICT",
        lambda: review.create_candidate_revision(
            r.db,
            r.user.id,
            first["candidate_id"],
            data.model_copy(update={"expected_version": 1}),
            revision_key,
            policy=r.policy,
            integrity=r.integrity,
        ),
    )
    assert count(r, ExtractionBatch) == 1 and count(r, ContentRevision) == before


@pytest.mark.parametrize(
    "field",
    ["payload", "source_scope_id", "family_member_id", "derivation_profile", "required_purposes"],
)
def test_supp_b15_content_binding_tampering_rejected(records, field):
    r = records
    args = {
        "payload": payload("  合成🙂e\u0301 " * 100),
        "source_scope_id": r.source.id,
        "family_member_id": r.member.id,
        "derivation_profile": "raw_manual",
        "required_purposes": (),
    }
    signed = r.integrity.content_digest(**args)
    changed = dict(args)
    changed[field] = {
        "payload": payload("Different synthetic text"),
        "source_scope_id": uuid.uuid4(),
        "family_member_id": uuid.uuid4(),
        "derivation_profile": "ai_derived",
        "required_purposes": ("ai_analysis",),
    }[field]
    error(
        "CONTENT_RESTRICTED",
        lambda: r.integrity.verify_content(
            **changed,
            digest=signed.digest,
            scheme=signed.scheme,
            key_id=signed.key_id,
        ),
    )
    r.integrity.verify_content(
        **args,
        digest=signed.digest,
        scheme=signed.scheme,
        key_id=signed.key_id,
    )


@pytest.mark.parametrize(
    "field",
    [
        "actor_user_id",
        "operation",
        "idempotency_key",
        "target_scope",
        "expected_versions",
        "payload",
    ],
)
def test_supp_b15_command_envelope_domains_and_binding(records, field):
    r = records
    args = {
        "actor_user_id": r.user.id,
        "operation": "memory.candidate.manual",
        "idempotency_key": uuid.uuid4(),
        "target_scope": {"member": r.member.id, "source": r.source.id},
        "expected_versions": {"version": 0},
        "payload": {"content": "  合成🙂e\u0301 " * 100},
    }
    original = r.integrity.fingerprint(**args)
    changed = dict(args)
    changed[field] = {
        "actor_user_id": r.other.id,
        "operation": "memory.revise",
        "idempotency_key": uuid.uuid4(),
        "target_scope": {"member": uuid.uuid4()},
        "expected_versions": {"version": 1},
        "payload": {"content": "different"},
    }[field]
    assert original.digest != r.integrity.fingerprint(**changed).digest
    assert r.integrity.fingerprint(**args).digest == original.digest
    assert len(original.digest) == 32 and original.scheme == "memory-command.v1"
    error(
        "MEMORY_INTEGRITY_UNAVAILABLE",
        lambda: r.integrity.fingerprint(**args, scheme="control-sha256.v1"),
    )


def _supp_proposal_state(r, state):
    from datetime import UTC, datetime

    created = manual(r)
    if state in {"submitted", "rejected", "approved"}:
        submit(r, created)
    if state == "approved":
        review.approve(
            r.db,
            r.user.id,
            created["proposal_id"],
            ProposalApprove(expected_version=1, expected_target_version=0),
            uuid.uuid4(),
            policy=r.policy,
            integrity=r.integrity,
        )
    elif state == "rejected":
        review.reject(
            r.db,
            r.user.id,
            created["proposal_id"],
            ProposalReject(expected_version=1),
            uuid.uuid4(),
        )
    elif state == "withdrawn":
        review.withdraw(
            r.db,
            r.user.id,
            created["proposal_id"],
            VersionCommand(expected_version=0),
            uuid.uuid4(),
        )
    elif state in {"stale", "purged"}:
        values = {"state": state, "version": 2}
        if state == "stale":
            values.update(submitted_at=datetime.now(UTC), decided_at=datetime.now(UTC))
        r.db.execute(
            update(RevisionProposal)
            .where(RevisionProposal.id == created["proposal_id"])
            .values(**values)
        )
        r.db.commit()
    return created, r.db.get(RevisionProposal, created["proposal_id"])


_SUPP_ILLEGAL = [
    (state, action)
    for state in ("draft", "submitted", "approved", "rejected", "withdrawn", "stale", "purged")
    for action in ("submit", "approve", "reject", "withdraw")
    if (state, action)
    not in {
        ("draft", "submit"),
        ("submitted", "approve"),
        ("submitted", "reject"),
        ("draft", "withdraw"),
        ("submitted", "withdraw"),
        ("draft", "approve"),
        ("draft", "reject"),  # Already tested.
    }
]


@pytest.mark.parametrize("state,action", _SUPP_ILLEGAL)
def test_supp_b27_all_remaining_illegal_proposal_edges(records, state, action):
    r = records
    created, proposal = _supp_proposal_state(r, state)
    target = r.db.get(MemoryCandidate, created["candidate_id"])
    before = (
        proposal.state,
        proposal.version,
        proposal.input_revision_id,
        count(r, CommandIdempotencyRecord),
    )
    args = {"expected_version": proposal.version}
    if action in {"submit", "approve"}:
        args["expected_target_version"] = target.version
    data = {
        "submit": ProposalSubmit,
        "approve": ProposalApprove,
        "reject": ProposalReject,
        "withdraw": VersionCommand,
    }[action](**args)
    kwargs = (
        {"policy": r.policy, "integrity": r.integrity} if action in {"submit", "approve"} else {}
    )
    error(
        "PROPOSAL_STATE_CONFLICT",
        lambda: getattr(review, action)(
            r.db,
            r.user.id,
            proposal.id,
            data,
            uuid.uuid4(),
            **kwargs,
        ),
    )
    r.db.expire_all()
    row = r.db.get(RevisionProposal, proposal.id)
    assert (
        row.state,
        row.version,
        row.input_revision_id,
        count(r, CommandIdempotencyRecord),
    ) == before
    assert r.db.get(ContentRevision, created["revision_id"]).payload == payload().model_dump(
        mode="json"
    )


@pytest.mark.parametrize("state", ["draft", "submitted"])
def test_supp_b36_withdraw_without_capabilities(records, state):
    r = records
    created, proposal = _supp_proposal_state(r, state)
    r.keys.keys.clear()
    r.policy.decisions.clear()
    result, status = review.withdraw(
        r.db,
        r.user.id,
        proposal.id,
        VersionCommand(expected_version=proposal.version),
        uuid.uuid4(),
    )
    assert status == 200 and result["state"] == "withdrawn"
    assert count(r, Memory) == 0
    assert r.db.get(ContentRevision, created["revision_id"]).payload == payload().model_dump(
        mode="json"
    )


def test_supp_b28_rejected_revision_has_new_proposal(records):
    r = records
    created, old = _supp_proposal_state(r, "rejected")
    old_digest = old.payload_digest
    revised, status = review.create_candidate_revision(
        r.db,
        r.user.id,
        created["candidate_id"],
        RevisionCreate(
            expected_version=0,
            parent_revision_id=created["revision_id"],
            payload=payload("Synthetic correction after rejection"),
        ),
        uuid.uuid4(),
        policy=r.policy,
        integrity=r.integrity,
    )
    assert status == 201 and revised["proposal_id"] != old.id
    assert r.db.get(RevisionProposal, old.id).state == "rejected"
    assert r.db.get(RevisionProposal, old.id).payload_digest == old_digest
    assert r.db.get(ContentRevision, created["revision_id"]).payload == payload().model_dump(
        mode="json"
    )


def test_supp_b35_approval_commit_fault_is_unknown_and_atomic(records, monkeypatch):
    r = records
    created = manual(r)
    submit(r, created)
    monkeypatch.setattr(r.db, "commit", Mock(side_effect=RuntimeError("Synthetic commit boundary")))
    failure = error(
        "COMMAND_OUTCOME_UNKNOWN",
        lambda: review.approve(
            r.db,
            r.user.id,
            created["proposal_id"],
            ProposalApprove(expected_version=1, expected_target_version=0),
            uuid.uuid4(),
            policy=r.policy,
            integrity=r.integrity,
        ),
    )
    assert (
        failure.details["outcome"] == "unknown"
    )  # Injected before commit, not a PG transport test.
    r.db.expire_all()
    assert count(r, Memory) == 0 and count(r, ContentRevision) == 1
    assert r.db.get(RevisionProposal, created["proposal_id"]).state == "submitted"
    assert r.db.get(MemoryCandidate, created["candidate_id"]).promoted_memory_id is None
    assert r.db.get(InterviewMessage, r.source.id).content == " 合成：小时候常在河边坐着。 "


@pytest.mark.parametrize("phase", ["flush", "commit"])
def test_supp_b52_protected_failure_classification_at_both_boundaries(records, monkeypatch, phase):
    r = records
    created = manual(r)
    # Trusted diagnostics are synthetic. This verifies classification/rollback, not a PG race.
    failure = IntegrityError(
        "Synthetic private SQL",
        {},
        SimpleNamespace(
            sqlstate="23503",
            diag=SimpleNamespace(table_name="memory_candidates", constraint_name="fk_mc_source"),
        ),
    )
    deleting = Mock(return_value=True)
    if phase == "flush":
        deleting.side_effect = failure
    else:
        monkeypatch.setattr(r.db, "commit", Mock(side_effect=failure))
    rollback = Mock(wraps=r.db.rollback)
    monkeypatch.setattr(r.db, "rollback", rollback)
    result = error(
        "RESOURCE_IN_USE",
        lambda: interview_service._delete_with_reference_guard(
            r.db,
            has_references=lambda: False,
            delete=deleting,
            constraint_names=set(),
            reauthorize=lambda: review.member_scope(r.db, r.user.id, r.member.id),
        ),
    )
    assert result.status_code == 409 and rollback.called
    assert r.db.get(InterviewMessage, r.source.id).content == " 合成：小时候常在河边坐着。 "
    assert r.db.get(MemoryCandidate, created["candidate_id"]) is not None


@pytest.mark.parametrize(
    "state", ["draft", "submitted", "approved", "rejected", "withdrawn", "stale", "purged"]
)
@pytest.mark.parametrize("kind", ["interview", "member", "family"])
def test_supp_b50_revision_and_proposal_states_protect_sources(records, state, kind):
    r = records
    created, proposal = _supp_proposal_state(r, state)
    callbacks = {
        "interview": lambda: interview_service.delete_interview(
            r.db, user_id=r.user.id, interview_id=r.interview.id
        ),
        "member": lambda: member_service.delete_family_member(
            r.db, user_id=r.user.id, family_id=r.family.id, member_id=r.member.id
        ),
        "family": lambda: family_service.delete_family(
            r.db, user_id=r.user.id, family_id=r.family.id
        ),
    }
    error("RESOURCE_IN_USE", callbacks[kind])
    r.db.expire_all()
    assert r.db.get(RevisionProposal, proposal.id).state == state
    assert r.db.get(ContentRevision, created["revision_id"]) is not None
    assert r.db.get(InterviewMessage, r.source.id).content == " 合成：小时候常在河边坐着。 "


@pytest.mark.parametrize("action", ["submit", "approve", "reject", "withdraw", "revise", "cancel"])
def test_supp_b56_existing_target_version_mismatch_is_atomic(records, action):
    r = records
    created = manual(r)
    if action in {"approve", "reject"}:
        submit(r, created)
    before = (count(r, CommandIdempotencyRecord), count(r, ContentRevision), count(r, Memory))
    if action == "cancel":
        batch = extract(r)
        before = (count(r, CommandIdempotencyRecord), count(r, ContentRevision), count(r, Memory))
        callback = lambda: extraction.cancel_batch(
            r.db, r.user.id, batch["batch_id"], VersionCommand(expected_version=999), uuid.uuid4()
        )
    elif action == "revise":
        callback = lambda: review.create_candidate_revision(
            r.db,
            r.user.id,
            created["candidate_id"],
            RevisionCreate(
                expected_version=999, parent_revision_id=created["revision_id"], payload=payload()
            ),
            uuid.uuid4(),
            policy=r.policy,
            integrity=r.integrity,
        )
    else:
        data_type = {
            "submit": ProposalSubmit,
            "approve": ProposalApprove,
            "reject": ProposalReject,
            "withdraw": VersionCommand,
        }[action]
        values = {"expected_version": 999}
        if action in {"submit", "approve"}:
            values["expected_target_version"] = 0
        kwargs = (
            {"policy": r.policy, "integrity": r.integrity}
            if action in {"submit", "approve"}
            else {}
        )
        callback = lambda: getattr(review, action)(
            r.db, r.user.id, created["proposal_id"], data_type(**values), uuid.uuid4(), **kwargs
        )
    error("VERSION_CONFLICT", callback)
    assert before == (
        count(r, CommandIdempotencyRecord),
        count(r, ContentRevision),
        count(r, Memory),
    )
