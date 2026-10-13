"""Synthetic SQLite Service/CRUD regressions, not HTTP/ASGI evidence.

Run through the guarded test_memory_workflow.py offline entrypoint. Each case
owns a fresh in-memory database; no conftest, client or application import.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.crud import memoir as memoir_crud
from app.database import models_import  # noqa: F401 -- register non-dormant models
from app.database.base import Base
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.interview import Interview
from app.models.interview_message import InterviewMessage
from app.models.interview_session import InterviewSession
from app.models.memoir import Memoir, MemoirSection
from app.models.memory import Memory
from app.models.memory_workflow import ContentRevision, MemoryCandidate, RevisionProposal
from app.models.user import User
from app.schemas.memoir import MemoirCreate, MemoirSectionReference
from app.schemas.memory import MemoryCreate, MemoryUpdate
from app.schemas.memory_workflow import (
    ManualCandidateCreate,
    ProposalApprove,
    ProposalSubmit,
    RevisionCreate,
    RevisionPayload,
)
from app.services import memoir as memoir_service
from app.services import memory as memory_service
from app.services import memory_review as review
from app.services.memory_integrity import MemoryIntegrity, SyntheticKeyProvider
from app.services.memory_policy import PURPOSES, DecisionStamp, SyntheticMemoryPolicy


@pytest.fixture
def records():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        assert db.bind.dialect.name == "sqlite"
        assert db.bind.url.database in (None, "", ":memory:")
        assert db.scalar(text("PRAGMA foreign_keys")) == 1
        owner = User(email="synthetic-owner@example.invalid", password_hash="fixture-unused")
        stranger = User(email="synthetic-stranger@example.invalid", password_hash="fixture-unused")
        db.add_all([owner, stranger])
        db.flush()
        family = Family(owner_id=owner.id, name="Synthetic family")
        other_family = Family(owner_id=stranger.id, name="Other synthetic family")
        db.add_all([family, other_family])
        db.flush()
        members = [
            FamilyMember(family_id=family.id, name="Subject"),
            FamilyMember(family_id=family.id, name="Other subject"),
            FamilyMember(family_id=other_family.id, name="Other owner subject"),
        ]
        db.add_all(members)
        db.flush()
        sources = []
        for person in members:
            interview = Interview(family_member_id=person.id, title="Synthetic interview")
            db.add(interview)
            db.flush()
            session = InterviewSession(interview_id=interview.id)
            db.add(session)
            db.flush()
            message = InterviewMessage(
                session_id=session.id,
                role="user",
                source="text",
                sequence=1,
                content="  合成：那一年我记不清。\n",
            )
            db.add(message)
            db.flush()
            sources.append((interview, session, message))
        legacy = Memory(
            family_member_id=members[0].id,
            source_message_id=sources[0][2].id,
            record_origin="legacy",
            title="  Legacy title  ",
            content="  合成 legacy\n",
            time_text=None,
            place=" 合成地方 ",
            emotion=None,
        )
        db.add(legacy)
        db.commit()
        decisions = {}
        for person, family_row, actor, (_interview, _session, message) in zip(
            members, (family, family, other_family), (owner, owner, stranger), sources, strict=True
        ):
            decisions[message.id] = DecisionStamp(
                operation="fixture",
                actor_user_id=actor.id,
                family_scope_id=family_row.id,
                family_member_id=person.id,
                source_scope_id=message.id,
                source_generation=1,
                required_purposes=tuple(sorted(PURPOSES)),
                purpose_generations={purpose: 1 for purpose in PURPOSES},
                allow=True,
                body_available=True,
                restore_verified=True,
            )
        yield SimpleNamespace(
            db=db,
            owner=owner,
            stranger=stranger,
            family=family,
            member=members[0],
            other_member=members[1],
            stranger_member=members[2],
            interview=sources[0][0],
            session=sources[0][1],
            message=sources[0][2],
            other_message=sources[1][2],
            stranger_message=sources[2][2],
            legacy=legacy,
            policy=SyntheticMemoryPolicy(decisions),
            integrity=MemoryIntegrity(
                SyntheticKeyProvider(
                    {"fixture-v1": b"synthetic-only-key-for-tests-00001"}, "fixture-v1"
                )
            ),
        )
        db.rollback()
    engine.dispose()


def payload(*, title=" 合成童年 ", content="  合成：年份并不确定。\n"):
    return RevisionPayload(
        title=title,
        content=content,
        time_text=None,
        place=None,
        emotion=None,
        uncertainties=["年份不确定"],
    )


def capabilities(r):
    return {"policy": r.policy, "integrity": r.integrity}


def approved(r, *, title=" 合成童年 ", content="  合成：年份并不确定。\n"):
    candidate, _ = review.manual_candidate(
        r.db,
        r.owner.id,
        r.member.id,
        ManualCandidateCreate(
            source_message_id=r.message.id, payload=payload(title=title, content=content)
        ),
        uuid4(),
        **capabilities(r),
    )
    review.submit(
        r.db,
        r.owner.id,
        candidate["proposal_id"],
        ProposalSubmit(expected_version=0, expected_target_version=0),
        uuid4(),
        **capabilities(r),
    )
    result, _ = review.approve(
        r.db,
        r.owner.id,
        candidate["proposal_id"],
        ProposalApprove(expected_version=1, expected_target_version=0),
        uuid4(),
        **capabilities(r),
    )
    return result


def memoir_request(*results, title=" 合成人生回忆 "):
    return MemoirCreate(
        title=title,
        sections=[
            MemoirSectionReference(
                memory_id=item["memory_id"],
                memory_revision_id=item["memory_revision_id"],
                approval_proposal_id=item["proposal_id"],
            )
            for item in results
        ],
    )


def make_memoir(r, *results):
    result, status = memoir_service.create(
        r.db, r.owner.id, r.member.id, memoir_request(*results), uuid4(), **capabilities(r)
    )
    assert status == 201
    return memoir_service.get(r.db, r.owner.id, result["memoir_id"])


def assert_error(code, callback, *, status=None):
    with pytest.raises(AppException) as caught:
        callback()
    assert caught.value.code == code
    if status is not None:
        assert caught.value.status_code == status
    return caught.value


def test_old_create_is_explicitly_disabled_without_new_headers(records):
    r = records
    assert_error(
        "REVISION_WORKFLOW_REQUIRED",
        lambda: memory_service.create(
            r.db,
            r.owner.id,
            r.member.id,
            MemoryCreate(source_message_id=r.message.id, title="Old", content="Old"),
        ),
        status=409,
    )
    assert r.db.scalar(select(Memory.id).where(Memory.id != r.legacy.id)) is None
    assert r.db.get(InterviewMessage, r.message.id).content == "  合成：那一年我记不清。\n"


def test_old_patch_disabled_preserves_legacy_bytes(records):
    r = records
    assert_error(
        "REVISION_WORKFLOW_REQUIRED",
        lambda: memory_service.update(
            r.db, r.owner.id, r.legacy.id, MemoryUpdate(content="Overwrite", place=None)
        ),
        status=409,
    )
    row = r.db.execute(
        select(Memory.title, Memory.content, Memory.place).where(Memory.id == r.legacy.id)
    ).one()
    assert tuple(row) == ("  Legacy title  ", "  合成 legacy\n", " 合成地方 ")


@pytest.mark.parametrize("operation", ["get", "list", "create", "update"])
def test_old_memory_operations_keep_cross_owner_404(records, operation):
    r = records
    calls = {
        "get": lambda: memory_service.get(r.db, r.stranger.id, r.legacy.id),
        "list": lambda: memory_service.list_for_member(r.db, r.stranger.id, r.member.id, 1, 20),
        "create": lambda: memory_service.create(
            r.db,
            r.stranger.id,
            r.member.id,
            MemoryCreate(source_message_id=r.message.id, title="x", content="x"),
        ),
        "update": lambda: memory_service.update(
            r.db, r.stranger.id, r.legacy.id, MemoryUpdate(title="x")
        ),
    }
    with pytest.raises(AppException) as caught:
        calls[operation]()
    assert caught.value.status_code == 404


def test_legacy_get_and_list_never_fallback_to_body(records):
    r = records
    result = memory_service.get(r.db, r.owner.id, r.legacy.id)
    assert result["current_content"] is None
    assert result["approval_state"] == "legacy_unreviewed"
    assert not {"title", "content", "time_text", "place", "emotion"} & result.keys()
    rows, total = memory_service.list_for_member(r.db, r.owner.id, r.member.id, 1, 1)
    assert total == 1 and rows[0]["id"] == r.legacy.id
    assert not {"title", "content", "current_content"} & rows[0].keys()
    assert memory_service.list_for_member(r.db, r.owner.id, r.member.id, 2, 1)[0] == []


def test_explicit_legacy_snapshot_preserves_whitespace(records):
    r = records
    result = memory_service.legacy_snapshot(r.db, r.owner.id, r.legacy.id, **capabilities(r))
    assert result["approved"] is False
    assert (result["title"], result["content"], result["place"]) == (
        "  Legacy title  ",
        "  合成 legacy\n",
        " 合成地方 ",
    )


def test_legacy_unknown_consent_is_restricted_even_for_owner(records):
    r = records
    r.policy.decisions.clear()
    assert_error(
        "CONTENT_RESTRICTED",
        lambda: memory_service.legacy_snapshot(r.db, r.owner.id, r.legacy.id, **capabilities(r)),
        status=403,
    )
    assert memory_service.get(r.db, r.owner.id, r.legacy.id)["current_content"] is None


@pytest.mark.parametrize("foreign", ["other_message", "stranger_message"])
def test_manual_candidate_retains_source_subject_owner_isolation(records, foreign):
    r = records
    source = getattr(r, foreign)
    with pytest.raises(AppException) as caught:
        review.manual_candidate(
            r.db,
            r.owner.id,
            r.member.id,
            ManualCandidateCreate(source_message_id=source.id, payload=payload()),
            uuid4(),
            **capabilities(r),
        )
    assert caught.value.status_code == 404
    assert r.db.scalar(select(MemoryCandidate.id)) is None


@pytest.mark.parametrize("role,source", [("assistant", "ai_generated"), ("system", "text")])
def test_non_original_manual_source_rejected(records, role, source):
    r = records
    r.message.role, r.message.source = role, source
    r.db.commit()
    assert_error(
        "INVALID_SOURCE",
        lambda: review.manual_candidate(
            r.db,
            r.owner.id,
            r.member.id,
            ManualCandidateCreate(source_message_id=r.message.id, payload=payload()),
            uuid4(),
            **capabilities(r),
        ),
        status=422,
    )


def test_manual_approval_traceability_and_no_body_on_memory_row(records):
    r = records
    result = approved(r)
    memory = r.db.get(Memory, result["memory_id"])
    revision = r.db.get(ContentRevision, result["memory_revision_id"])
    assert memory.source_message_id == r.message.id
    assert memory.current_approval_proposal_id == result["proposal_id"]
    assert memory.title is memory.content is None
    assert revision.source_scope_id == r.message.id and revision.origin_revision_id is not None
    assert (
        memory_service.get(r.db, r.owner.id, memory.id, **capabilities(r))["current_content"][
            "content"
        ]
        == "  合成：年份并不确定。\n"
    )
    assert r.db.get(InterviewMessage, r.message.id).content == "  合成：那一年我记不清。\n"


def test_memoir_exact_order_and_version_reference(records):
    r = records
    first, second = approved(r, title="第一章"), approved(r, title="第二章")
    memoir = make_memoir(r, second, first)
    result = memoir_service.content(r.db, r.owner.id, memoir["id"], **capabilities(r))
    assert result["title"] == " 合成人生回忆 "
    assert [item["position"] for item in result["sections"]] == [1, 2]
    assert [item["memory_id"] for item in result["sections"]] == [
        second["memory_id"],
        first["memory_id"],
    ]
    assert [item["memory_revision_id"] for item in result["sections"]] == [
        second["memory_revision_id"],
        first["memory_revision_id"],
    ]


def test_new_memory_approval_does_not_mutate_memoir_snapshot(records):
    r = records
    result = approved(r)
    memoir = make_memoir(r, result)
    old_content = memoir_service.content(r.db, r.owner.id, memoir["id"], **capabilities(r))
    draft, _ = review.create_memory_revision(
        r.db,
        r.owner.id,
        result["memory_id"],
        RevisionCreate(
            expected_version=1,
            parent_revision_id=result["memory_revision_id"],
            payload=payload(content="合成新版本"),
        ),
        uuid4(),
        **capabilities(r),
    )
    review.submit(
        r.db,
        r.owner.id,
        draft["proposal_id"],
        ProposalSubmit(expected_version=0, expected_target_version=1),
        uuid4(),
        **capabilities(r),
    )
    review.approve(
        r.db,
        r.owner.id,
        draft["proposal_id"],
        ProposalApprove(expected_version=1, expected_target_version=1),
        uuid4(),
        **capabilities(r),
    )
    assert memoir_service.content(r.db, r.owner.id, memoir["id"], **capabilities(r)) == old_content
    assert (
        memory_service.get(r.db, r.owner.id, result["memory_id"], **capabilities(r))[
            "current_content"
        ]["content"]
        == "合成新版本"
    )


def test_memoir_metadata_and_sections_never_return_body(records):
    r = records
    memoir = make_memoir(r, approved(r))
    assert (
        not {"title", "content", "sections"}
        & memoir_service.get(r.db, r.owner.id, memoir["id"]).keys()
    )
    sections, total = memoir_service.list_sections(r.db, r.owner.id, memoir["id"], 1, 20)
    assert total == 1 and not {"title", "content", "payload", "digest"} & sections[0].keys()


def test_cross_owner_memoir_all_service_reads(records):
    r = records
    memoir = make_memoir(r, approved(r))
    section = r.db.scalar(select(MemoirSection).where(MemoirSection.memoir_id == memoir["id"]))
    for call in (
        lambda: memoir_service.get(r.db, r.stranger.id, memoir["id"]),
        lambda: memoir_service.list_sections(r.db, r.stranger.id, memoir["id"], 1, 20),
        lambda: memoir_service.content(r.db, r.stranger.id, memoir["id"], **capabilities(r)),
        lambda: memoir_service.section_content(
            r.db, r.stranger.id, memoir["id"], section.id, **capabilities(r)
        ),
    ):
        with pytest.raises(AppException) as caught:
            call()
        assert caught.value.status_code == 404


def test_section_wrong_url_parent_is_404(records):
    r = records
    result = approved(r)
    first, second = make_memoir(r, result), make_memoir(r, result)
    section = r.db.scalar(select(MemoirSection).where(MemoirSection.memoir_id == first["id"]))
    with pytest.raises(AppException) as caught:
        memoir_service.section_content(
            r.db, r.owner.id, second["id"], section.id, **capabilities(r)
        )
    assert caught.value.status_code == 404


def test_memoir_rejects_unreviewed_or_mismatched_proof_atomically(records):
    r = records
    result = approved(r)
    bad = {**result, "memory_id": r.legacy.id}
    assert_error("INVALID_APPROVED_REVISION", lambda: make_memoir(r, result, bad), status=422)
    assert r.db.scalar(select(Memoir.id)) is None and r.db.scalar(select(MemoirSection.id)) is None


def test_memoir_legacy_memory_ids_and_duplicate_reference_rejected():
    identifier = uuid4()
    with pytest.raises(ValidationError):
        MemoirCreate(title="x", memory_ids=[identifier])
    reference = MemoirSectionReference(
        memory_id=identifier, memory_revision_id=uuid4(), approval_proposal_id=uuid4()
    )
    for references in ([], [reference, reference]):
        with pytest.raises(ValidationError):
            MemoirCreate(title="x", sections=references)


def test_memoir_write_failure_has_no_partial_parent_or_section(records, monkeypatch):
    r = records
    result = approved(r)
    original = memoir_crud.create

    def fail_after_flush(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic private failure")

    monkeypatch.setattr(memoir_crud, "create", fail_after_flush)
    with pytest.raises(AppException) as caught:
        make_memoir(r, result)
    assert caught.value.status_code == 503 and "private" not in caught.value.message
    assert r.db.scalar(select(Memoir.id)) is None and r.db.scalar(select(MemoirSection.id)) is None


def test_source_foreign_key_preserves_all_evidence_after_rollback(records):
    r = records
    result = approved(r)
    r.db.delete(r.message)
    with pytest.raises(IntegrityError):
        r.db.flush()
    r.db.rollback()
    assert r.db.get(InterviewMessage, r.message.id).content == "  合成：那一年我记不清。\n"
    assert r.db.get(Memory, result["memory_id"]) is not None
    assert r.db.get(ContentRevision, result["memory_revision_id"]) is not None


def test_withdrawn_source_blocks_current_and_historical_memoir_body(records):
    r = records
    result = approved(r)
    memoir = make_memoir(r, result)
    r.policy.decisions[r.message.id] = r.policy.decisions[r.message.id].model_copy(
        update={"allow": False}
    )
    for call in (
        lambda: memory_service.get(r.db, r.owner.id, result["memory_id"], **capabilities(r)),
        lambda: memoir_service.content(r.db, r.owner.id, memoir["id"], **capabilities(r)),
    ):
        assert_error("CONTENT_RESTRICTED", call, status=403)
    assert memoir_service.get(r.db, r.owner.id, memoir["id"])["section_count"] == 1
    assert r.db.get(RevisionProposal, result["proposal_id"]).state == "approved"


def test_reconsent_generation_does_not_restore_old_approval(records):
    r = records
    memoir = make_memoir(r, approved(r))
    r.policy.decisions[r.message.id] = r.policy.decisions[r.message.id].model_copy(
        update={"source_generation": 2, "allow": True, "restore_verified": True}
    )
    assert_error(
        "CONTENT_RESTRICTED",
        lambda: memoir_service.content(r.db, r.owner.id, memoir["id"], **capabilities(r)),
        status=403,
    )


def test_deleted_body_cannot_leak_via_preserved_section_snapshot(records):
    r = records
    memoir = make_memoir(r, approved(r))
    r.policy.decisions[r.message.id] = r.policy.decisions[r.message.id].model_copy(
        update={"body_available": False}
    )
    assert_error(
        "CONTENT_RESTRICTED",
        lambda: memoir_service.content(r.db, r.owner.id, memoir["id"], **capabilities(r)),
        status=403,
    )
    assert (
        r.db.scalar(select(MemoirSection.content).where(MemoirSection.memoir_id == memoir["id"]))
        == "  合成：年份并不确定。\n"
    )


def test_legacy_first_revision_does_not_rewrite_legacy_bytes(records):
    r = records
    draft, _ = review.create_memory_revision(
        r.db,
        r.owner.id,
        r.legacy.id,
        RevisionCreate(expected_version=0, parent_revision_id=None, payload=payload()),
        uuid4(),
        **capabilities(r),
    )
    assert r.db.get(ContentRevision, draft["revision_id"]).parent_revision_id is None
    assert memory_service.get(r.db, r.owner.id, r.legacy.id)["current_content"] is None
    assert r.db.scalar(select(Memory.content).where(Memory.id == r.legacy.id)) == "  合成 legacy\n"


def test_missing_ids_remain_owner_scoped_404(records):
    r = records
    for call in (
        lambda: memory_service.get(r.db, r.owner.id, uuid4()),
        lambda: memoir_service.get(r.db, r.owner.id, uuid4()),
        lambda: memoir_service.list_sections(r.db, r.owner.id, uuid4(), 1, 20),
    ):
        with pytest.raises(AppException) as caught:
            call()
        assert caught.value.status_code == 404


def test_legacy_memoir_snapshot_never_fabricates_revision_proof(records):
    r = records
    memoir = Memoir(
        family_member_id=r.member.id,
        title=" Legacy memoir ",
        record_origin="legacy",
        sections=[
            MemoirSection(
                memory_id=r.legacy.id,
                position=1,
                title=" Legacy section ",
                content=" Legacy section bytes\n",
                record_origin="legacy_snapshot",
            )
        ],
    )
    r.db.add(memoir)
    r.db.commit()
    result = memoir_service.content(r.db, r.owner.id, memoir.id, **capabilities(r))
    assert result["title"] == " Legacy memoir "
    assert result["sections"][0]["content"] == " Legacy section bytes\n"
    assert result["sections"][0]["memory_revision_id"] is None
    assert result["sections"][0]["approval_proposal_id"] is None
    r.policy.decisions.clear()
    assert_error(
        "CONTENT_RESTRICTED",
        lambda: memoir_service.content(r.db, r.owner.id, memoir.id, **capabilities(r)),
        status=403,
    )


@pytest.mark.parametrize("target", ["interview", "member", "family"])
def test_legacy_parent_deletion_preserves_memory_and_source(records, target):
    from app.services import family as family_service
    from app.services import family_member as member_service
    from app.services import interview as interview_service

    r = records
    callbacks = {
        "interview": lambda: interview_service.delete_interview(
            r.db, user_id=r.owner.id, interview_id=r.interview.id
        ),
        "member": lambda: member_service.delete_family_member(
            r.db, user_id=r.owner.id, family_id=r.family.id, member_id=r.member.id
        ),
        "family": lambda: family_service.delete_family(
            r.db, user_id=r.owner.id, family_id=r.family.id
        ),
    }
    with pytest.raises(AppException) as caught:
        callbacks[target]()
    assert caught.value.status_code == 409
    for row in (r.family, r.member, r.interview, r.session, r.message, r.legacy):
        assert r.db.get(type(row), row.id) is not None
    assert r.db.scalar(select(Memory.content).where(Memory.id == r.legacy.id)) == "  合成 legacy\n"
