import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.crud import memoir as memoir_crud
from app.models.interview_message import InterviewMessage
from app.models.memoir import Memoir, MemoirSection
from app.schemas.memoir import MemoirCreate
from app.services import memoir as memoir_service
from tests.test_interview_message import _register_and_login


def setup_member(client, headers, family_id=None):
    if family_id is None:
        family_id = client.post(
            "/api/v1/families", json={"name": "Family"}, headers=headers
        ).json()["id"]
    member = client.post(
        f"/api/v1/families/{family_id}/members", json={"name": "Person"}, headers=headers
    ).json()
    interview = client.post(
        f"/api/v1/family-members/{member['id']}/interviews",
        json={"title": "Interview"},
        headers=headers,
    ).json()
    session = client.post(
        f"/api/v1/interviews/{interview['id']}/sessions", json={}, headers=headers
    ).json()
    message = client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"content": "我十岁左右住在上海。"},
        headers=headers,
    ).json()
    return member["id"], message, family_id


def create_memory(client, headers, member, message, title="童年"):
    return client.post(
        f"/api/v1/family-members/{member}/memories",
        headers=headers,
        json={
            "source_message_id": message["id"],
            "title": title,
            "content": "童年住在上海。",
            "time_text": "十岁左右",
            "place": "上海",
        },
    )


def test_memory_crud_and_traceability(client, db_session):
    headers = _register_and_login(client, "owner@example.com")
    member, message, _ = setup_member(client, headers)
    response = create_memory(client, headers, member, message)
    assert response.status_code == 201
    memory = response.json()
    assert memory["family_member_id"] == member
    assert memory["source_message_id"] == message["id"]
    assert client.get(f"/api/v1/memories/{memory['id']}", headers=headers).json() == memory
    listing = client.get(
        f"/api/v1/family-members/{member}/memories?page=1&page_size=1", headers=headers
    ).json()
    assert listing["total"] == 1 and listing["items"][0]["id"] == memory["id"]
    assert (
        client.get(
            f"/api/v1/family-members/{member}/memories?page=2&page_size=1", headers=headers
        ).json()["items"]
        == []
    )
    updated = client.patch(
        f"/api/v1/memories/{memory['id']}",
        json={"content": "人工整理的另一种表达", "place": None},
        headers=headers,
    )
    assert updated.status_code == 200 and updated.json()["place"] is None
    assert updated.json()["source_message_id"] == message["id"]
    source = db_session.get(InterviewMessage, uuid.UUID(message["id"]))
    assert source.content == message["content"] and str(source.session_id) == message["session_id"]


def test_memoir_order_and_snapshot(client):
    headers = _register_and_login(client, "owner@example.com")
    member, message, _ = setup_member(client, headers)
    first = create_memory(client, headers, member, message, "第一章").json()
    second = create_memory(client, headers, member, message, "第二章").json()
    response = client.post(
        f"/api/v1/family-members/{member}/memoirs",
        headers=headers,
        json={"title": "人生回忆", "memory_ids": [second["id"], first["id"]]},
    )
    assert response.status_code == 201
    memoir = response.json()
    assert memoir["status"] == "draft"
    assert [s["position"] for s in memoir["sections"]] == [1, 2]
    assert [s["memory_id"] for s in memoir["sections"]] == [second["id"], first["id"]]
    client.patch(f"/api/v1/memories/{second['id']}", headers=headers, json={"content": "已更新"})
    fetched = client.get(f"/api/v1/memoirs/{memoir['id']}", headers=headers).json()
    assert fetched == memoir
    sections = client.get(f"/api/v1/memoirs/{memoir['id']}/sections", headers=headers).json()
    assert sections == {"total": 2, "items": memoir["sections"]}


@pytest.mark.parametrize("same_family", [True, False])
def test_cross_member_sources_and_memories_rejected(client, same_family):
    headers = _register_and_login(client, "owner@example.com")
    member, _message, family = setup_member(client, headers)
    other, other_message, _ = setup_member(client, headers, family if same_family else None)
    assert create_memory(client, headers, member, other_message).status_code == 404
    other_memory = create_memory(client, headers, other, other_message).json()
    response = client.post(
        f"/api/v1/family-members/{member}/memoirs",
        headers=headers,
        json={"title": "Draft", "memory_ids": [other_memory["id"]]},
    )
    assert response.status_code == 404
    assert (
        client.get(f"/api/v1/family-members/{member}/memories", headers=headers).json()["total"]
        == 0
    )


def test_cross_user_all_endpoints(client):
    owner = _register_and_login(client, "owner@example.com")
    stranger = _register_and_login(client, "stranger@example.com")
    member, message, _ = setup_member(client, owner)
    own_member, _, _ = setup_member(client, stranger)
    memory = create_memory(client, owner, member, message).json()
    memoir = client.post(
        f"/api/v1/family-members/{member}/memoirs",
        headers=owner,
        json={"title": "Draft", "memory_ids": [memory["id"]]},
    ).json()
    for path in [
        f"/memories/{memory['id']}",
        f"/family-members/{member}/memories",
        f"/memoirs/{memoir['id']}",
        f"/memoirs/{memoir['id']}/sections",
    ]:
        response = client.get("/api/v1" + path, headers=stranger)
        assert response.status_code == 404 and response.json()["error"]["code"] == "NOT_FOUND"
    assert (
        client.patch(
            f"/api/v1/memories/{memory['id']}", headers=stranger, json={"title": "Intruder"}
        ).status_code
        == 404
    )
    assert create_memory(client, stranger, member, message).status_code == 404
    assert create_memory(client, stranger, own_member, message).status_code == 404
    assert (
        client.post(
            f"/api/v1/family-members/{own_member}/memoirs",
            headers=stranger,
            json={"title": "Draft", "memory_ids": [memory["id"]]},
        ).status_code
        == 404
    )


def test_missing_records_and_validation(client):
    headers = _register_and_login(client, "owner@example.com")
    member, message, _ = setup_member(client, headers)
    missing = str(uuid.uuid4())
    assert create_memory(client, headers, member, {"id": missing}).status_code == 404
    assert create_memory(client, headers, member, {"id": "invalid"}).status_code == 422
    assert create_memory(client, headers, missing, message).status_code == 404
    for path in [
        f"/memories/{missing}",
        f"/memoirs/{missing}",
        f"/memoirs/{missing}/sections",
        f"/family-members/{missing}/memories",
    ]:
        response = client.get("/api/v1" + path, headers=headers)
        assert response.status_code == 404 and response.json()["error"]["code"] == "NOT_FOUND"
    assert (
        client.patch(
            f"/api/v1/memories/{missing}", headers=headers, json={"title": "Missing"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/family-members/{member}/memoirs",
            headers=headers,
            json={"title": "Draft", "memory_ids": [missing]},
        ).status_code
        == 404
    )
    memory = create_memory(client, headers, member, message).json()
    for data in [
        {"title": None},
        {"content": "   "},
        {"source_message_id": missing},
        {"user_id": missing},
    ]:
        assert (
            client.patch(f"/api/v1/memories/{memory['id']}", json=data, headers=headers).status_code
            == 422
        )
    for ids in [[], [memory["id"], memory["id"]]]:
        assert (
            client.post(
                f"/api/v1/family-members/{member}/memoirs",
                headers=headers,
                json={"title": "Draft", "memory_ids": ids},
            ).status_code
            == 422
        )


def test_non_original_source_rejected(client, db_session):
    headers = _register_and_login(client, "owner@example.com")
    member, message, _ = setup_member(client, headers)
    source = db_session.get(InterviewMessage, uuid.UUID(message["id"]))
    source.role, source.source = "assistant", "ai_generated"
    db_session.commit()
    response = create_memory(client, headers, member, message)
    assert response.status_code == 400 and response.json()["error"]["code"] == "INVALID_SOURCE"


def test_authentication_required(client):
    missing = uuid.uuid4()
    requests = [
        ("get", f"/memories/{missing}", None),
        ("patch", f"/memories/{missing}", {"title": "x"}),
        ("get", f"/family-members/{missing}/memories", None),
        (
            "post",
            f"/family-members/{missing}/memories",
            {"title": "x", "content": "x", "source_message_id": str(missing)},
        ),
        (
            "post",
            f"/family-members/{missing}/memoirs",
            {"title": "x", "memory_ids": [str(missing)]},
        ),
        ("get", f"/memoirs/{missing}", None),
        ("get", f"/memoirs/{missing}/sections", None),
    ]
    for method, path, data in requests:
        kwargs = {"json": data} if data is not None else {}
        assert getattr(client, method)("/api/v1" + path, **kwargs).status_code == 401


def test_memoir_failed_write_rolls_back(client, db_session, monkeypatch):
    headers = _register_and_login(client, "owner@example.com")
    member, message, _ = setup_member(client, headers)
    memory = create_memory(client, headers, member, message).json()
    original = memoir_crud.create

    def fail_after_flush(*args):
        original(*args)
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(memoir_crud, "create", fail_after_flush)
    from app.crud.user import get_user_by_email

    user = get_user_by_email(db_session, "owner@example.com")
    with pytest.raises(RuntimeError, match="synthetic failure"):
        memoir_service.create(
            db_session,
            user.id,
            uuid.UUID(member),
            MemoirCreate(title="Draft", memory_ids=[memory["id"]]),
        )
    assert list(db_session.scalars(select(Memoir))) == []
    assert list(db_session.scalars(select(MemoirSection))) == []


def test_source_foreign_key_preserves_evidence(client, db_session):
    headers = _register_and_login(client, "owner@example.com")
    member, message, _ = setup_member(client, headers)
    assert create_memory(client, headers, member, message).status_code == 201
    source = db_session.get(InterviewMessage, uuid.UUID(message["id"]))
    db_session.delete(source)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
    assert db_session.get(InterviewMessage, uuid.UUID(message["id"])).content == message["content"]


def test_memory_failed_write_rolls_back(client, db_session, monkeypatch):
    from app.crud import memory as memory_crud
    from app.crud.user import get_user_by_email
    from app.models.memory import Memory
    from app.schemas.memory import MemoryCreate
    from app.services import memory as memory_service

    headers = _register_and_login(client, "owner@example.com")
    member, message, _ = setup_member(client, headers)
    original = memory_crud.create

    def fail_after_flush(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(memory_crud, "create", fail_after_flush)
    user = get_user_by_email(db_session, "owner@example.com")
    with pytest.raises(RuntimeError, match="synthetic failure"):
        memory_service.create(
            db_session,
            user.id,
            uuid.UUID(member),
            MemoryCreate(title="Memory", content="Narrative", source_message_id=message["id"]),
        )
    assert list(db_session.scalars(select(Memory))) == []
    assert db_session.get(InterviewMessage, uuid.UUID(message["id"])).content == message["content"]


@pytest.fixture()
def remediation_records(db_session):
    from sqlalchemy import text

    from app.models.family import Family
    from app.models.family_member import FamilyMember
    from app.models.interview import Interview
    from app.models.interview_session import InterviewSession
    from app.models.memory import Memory
    from app.models.user import User

    assert db_session.bind.dialect.name == "sqlite"
    assert db_session.bind.url.database in (None, "", ":memory:")
    assert db_session.scalar(text("PRAGMA foreign_keys")) == 1
    owner = User(email="owner@example.com", password_hash="synthetic-unused-hash")
    stranger = User(email="stranger@example.com", password_hash="synthetic-unused-hash")
    db_session.add_all([owner, stranger])
    db_session.flush()
    family = Family(owner_id=owner.id, name="Family")
    db_session.add(family)
    db_session.flush()
    member = FamilyMember(family_id=family.id, name="Subject")
    db_session.add(member)
    db_session.flush()
    interview = Interview(family_member_id=member.id, title="Original interview")
    db_session.add(interview)
    db_session.flush()
    session = InterviewSession(interview_id=interview.id)
    db_session.add(session)
    db_session.flush()
    message = InterviewMessage(
        session_id=session.id, role="user", source="text", content="Original words", sequence=1
    )
    db_session.add(message)
    db_session.flush()
    memory = Memory(
        family_member_id=member.id,
        source_message_id=message.id,
        title="Memory",
        content="Manual summary",
    )
    db_session.add(memory)
    db_session.commit()
    return owner, stranger, family, member, interview, session, message, memory


@pytest.mark.parametrize("target", ["interview", "member"])
def test_remediation_service_delete_preserves_all(db_session, remediation_records, target):
    from app.core.exceptions import AppException
    from app.services import family_member as member_service
    from app.services import interview as interview_service

    owner, stranger, family, member, interview, session, message, memory = remediation_records
    with pytest.raises(AppException) as denied:
        if target == "interview":
            interview_service.delete_interview(
                db_session, user_id=stranger.id, interview_id=interview.id
            )
        else:
            member_service.delete_family_member(
                db_session, user_id=stranger.id, family_id=family.id, member_id=member.id
            )
    assert denied.value.status_code == 404
    with pytest.raises(AppException) as conflict:
        if target == "interview":
            interview_service.delete_interview(
                db_session, user_id=owner.id, interview_id=interview.id
            )
        else:
            member_service.delete_family_member(
                db_session, user_id=owner.id, family_id=family.id, member_id=member.id
            )
    assert conflict.value.status_code == 409 and conflict.value.code == "RESOURCE_IN_USE"
    for record in (member, interview, session, message, memory):
        assert db_session.get(type(record), record.id) is not None
    assert message.content == "Original words"
    interview.title = "Session remains usable"
    db_session.commit()
    assert db_session.get(type(interview), interview.id).title == "Session remains usable"


@pytest.mark.parametrize("target", ["interview", "member"])
def test_remediation_service_unreferenced_delete(db_session, remediation_records, target):
    from app.services import family_member as member_service
    from app.services import interview as interview_service

    owner, _, family, member, interview, _, _, memory = remediation_records
    target_id = interview.id if target == "interview" else member.id
    target_type = type(interview) if target == "interview" else type(member)
    db_session.delete(memory)
    db_session.commit()
    if target == "interview":
        interview_service.delete_interview(db_session, user_id=owner.id, interview_id=target_id)
    else:
        # Legacy ORM cannot delete a Member with Interviews (nullable FK mismatch).
        # Delete that unreferenced subtree first, matching existing empty-member tests.
        interview_service.delete_interview(db_session, user_id=owner.id, interview_id=interview.id)
        member_service.delete_family_member(
            db_session, user_id=owner.id, family_id=family.id, member_id=target_id
        )
    db_session.expire_all()
    assert db_session.get(target_type, target_id) is None


def test_remediation_service_actual_sqlite_flush_conflict(
    db_session, remediation_records, monkeypatch
):
    from app.core.exceptions import AppException
    from app.crud import interview as interview_crud
    from app.services import interview as interview_service

    owner, _, _, _, interview, session, message, memory = remediation_records
    original = interview_crud.has_protected_references
    calls = []

    def raced_references(*args, **kwargs):
        calls.append(1)
        return False if len(calls) == 1 else original(*args, **kwargs)

    monkeypatch.setattr(interview_crud, "has_protected_references", raced_references)
    with pytest.raises(AppException) as conflict:
        interview_service.delete_interview(db_session, user_id=owner.id, interview_id=interview.id)
    assert conflict.value.status_code == 409 and len(calls) == 2
    for record in (interview, session, message, memory):
        assert db_session.get(type(record), record.id) is not None
    interview.title = "Usable after real FK rollback"
    db_session.commit()


@pytest.mark.parametrize("stage", ["flush", "commit"])
@pytest.mark.parametrize(
    "state,name,expected",
    [
        ("23503", "memories_source_message_id_fkey", 409),
        ("23503", "unrelated_fk", None),
        ("23505", "memories_source_message_id_fkey", None),
    ],
)
def test_remediation_service_constraint_classification(
    db_session, remediation_records, monkeypatch, stage, state, name, expected
):
    from types import SimpleNamespace

    from app.core.exceptions import AppException
    from app.services.interview import _delete_with_reference_guard

    interview = remediation_records[4]

    class DriverError(Exception):
        sqlstate = state
        diag = SimpleNamespace(constraint_name=name, table_name="memories")

    error = IntegrityError("synthetic statement", {}, DriverError("private raw details"))
    old_title = interview.title

    def fail():
        raise error

    monkeypatch.setattr(db_session, stage, fail)

    def attempt_delete():
        interview.title = "Must roll back"
        db_session.flush()

    with pytest.raises(AppException if expected else IntegrityError) as caught:
        _delete_with_reference_guard(
            db_session,
            has_references=lambda: False,
            delete=attempt_delete,
            constraint_names={"memories_source_message_id_fkey"},
        )
    if expected:
        assert caught.value.status_code == expected
        assert "private raw details" not in caught.value.message
    else:
        assert caught.value is error
    monkeypatch.undo()
    assert db_session.get(type(interview), interview.id).title == old_title
    assert db_session.is_active


def test_remediation_service_nondisclosing_errors(db_session, remediation_records):
    import json

    from app.core.exceptions import AppException, app_exception_handler
    from app.schemas.memory import MemoryUpdate
    from app.services import memory as memory_service

    owner, stranger, _, member, _, _, _, memory = remediation_records
    memoir = memoir_service.create(
        db_session, owner.id, member.id, MemoirCreate(title="Draft", memory_ids=[memory.id])
    )
    operations = [
        (lambda actor, resource: memory_service.get(db_session, actor, resource), memory.id),
        (
            lambda actor, resource: memory_service.update(
                db_session, actor, resource, MemoryUpdate(title="New title")
            ),
            memory.id,
        ),
        (lambda actor, resource: memoir_service.get(db_session, actor, resource), memoir.id),
    ]
    for operation, resource_id in operations:
        bodies = []
        for resource in (resource_id, uuid.uuid4()):
            with pytest.raises(AppException) as caught:
                operation(stranger.id, resource)
            coroutine = app_exception_handler(None, caught.value)
            with pytest.raises(StopIteration) as returned:
                coroutine.send(None)
            response = returned.value.value
            assert response.status_code == 404
            bodies.append(json.loads(response.body))
        assert bodies[0] == bodies[1]
    assert memory_service.get(db_session, owner.id, memory.id).content == "Manual summary"
    assert memoir_service.get(db_session, owner.id, memoir.id).sections[0].memory_id == memory.id


def test_remediation_api_identical_404_bodies(client):
    owner = _register_and_login(client, "owner@example.com")
    stranger = _register_and_login(client, "stranger@example.com")
    member, message, _ = setup_member(client, owner)
    memory = create_memory(client, owner, member, message).json()
    memoir = client.post(
        f"/api/v1/family-members/{member}/memoirs",
        headers=owner,
        json={"title": "Draft", "memory_ids": [memory["id"]]},
    ).json()
    for method, pattern, resource in [
        ("get", "/memories/{}", memory["id"]),
        ("patch", "/memories/{}", memory["id"]),
        ("get", "/memoirs/{}", memoir["id"]),
        ("get", "/memoirs/{}/sections", memoir["id"]),
    ]:
        kwargs = {"json": {"title": "Attempt"}} if method == "patch" else {}
        existing = getattr(client, method)(
            "/api/v1" + pattern.format(resource), headers=stranger, **kwargs
        )
        missing = getattr(client, method)(
            "/api/v1" + pattern.format(uuid.uuid4()), headers=stranger, **kwargs
        )
        assert existing.status_code == missing.status_code == 404
        assert existing.json() == missing.json()
    assert client.get(f"/api/v1/memories/{memory['id']}", headers=owner).status_code == 200
    assert client.get(f"/api/v1/memoirs/{memoir['id']}", headers=owner).status_code == 200


@pytest.mark.parametrize("target", ["interview", "member"])
def test_remediation_api_delete_conflict(client, db_session, target):
    from app.models.interview import Interview
    from app.models.interview_session import InterviewSession
    from app.models.memory import Memory

    owner = _register_and_login(client, "owner@example.com")
    member, message, family = setup_member(client, owner)
    memory = create_memory(client, owner, member, message).json()
    source = db_session.get(InterviewMessage, uuid.UUID(message["id"]))
    session = db_session.get(InterviewSession, source.session_id)
    interview = db_session.get(Interview, session.interview_id)
    path = (
        f"/interviews/{interview.id}"
        if target == "interview"
        else f"/families/{family}/members/{member}"
    )
    response = client.delete("/api/v1" + path, headers=owner)
    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "RESOURCE_IN_USE",
        "message": "Resource is referenced and cannot be deleted",
        "details": None,
    }
    assert db_session.get(Interview, interview.id) is not None
    assert db_session.get(InterviewSession, session.id) is not None
    assert db_session.get(InterviewMessage, source.id).content == message["content"]
    assert db_session.get(Memory, uuid.UUID(memory["id"])) is not None
    assert (
        client.patch(
            f"/api/v1/memories/{memory['id']}", headers=owner, json={"title": "Still usable"}
        ).status_code
        == 200
    )


@pytest.mark.parametrize("same_family", [True, False])
def test_remediation_service_member_isolation(db_session, remediation_records, same_family):
    from app.core.exceptions import AppException
    from app.models.family import Family
    from app.models.family_member import FamilyMember
    from app.schemas.memory import MemoryCreate
    from app.services import memory as memory_service

    owner, _, family, _, _, _, message, memory = remediation_records
    if not same_family:
        family = Family(owner_id=owner.id, name="Other family")
        db_session.add(family)
        db_session.flush()
    other = FamilyMember(family_id=family.id, name="Other subject")
    db_session.add(other)
    db_session.commit()
    with pytest.raises(AppException) as source_error:
        memory_service.create(
            db_session,
            owner.id,
            other.id,
            MemoryCreate(title="Memory", content="Summary", source_message_id=message.id),
        )
    assert source_error.value.status_code == 404
    with pytest.raises(AppException) as memoir_error:
        memoir_service.create(
            db_session, owner.id, other.id, MemoirCreate(title="Draft", memory_ids=[memory.id])
        )
    assert memoir_error.value.status_code == 404
    assert memory_service.list_for_member(db_session, owner.id, other.id, 1, 20) == ([], 0)
    assert message.content == "Original words"


def test_remediation_service_snapshot_and_pagination(db_session, remediation_records):
    from app.schemas.memory import MemoryCreate, MemoryUpdate
    from app.services import memory as memory_service

    owner, _, _, member, _, _, message, first = remediation_records
    second = memory_service.create(
        db_session,
        owner.id,
        member.id,
        MemoryCreate(title="Second", content="Second content", source_message_id=message.id),
    )
    memoir = memoir_service.create(
        db_session,
        owner.id,
        member.id,
        MemoirCreate(title="Draft", memory_ids=[second.id, first.id]),
    )
    assert [section.memory_id for section in memoir.sections] == [second.id, first.id]
    assert [section.position for section in memoir.sections] == [1, 2]
    memory_service.update(db_session, owner.id, second.id, MemoryUpdate(content="Updated summary"))
    db_session.expire_all()
    assert (
        memoir_service.get(db_session, owner.id, memoir.id).sections[0].content == "Second content"
    )
    assert memory_service.get(db_session, owner.id, second.id).source_message_id == message.id
    first_page, total = memory_service.list_for_member(db_session, owner.id, member.id, 1, 1)
    second_page, _ = memory_service.list_for_member(db_session, owner.id, member.id, 2, 1)
    assert total == 2 and len(first_page) == len(second_page) == 1
    assert first_page[0].id != second_page[0].id
    assert message.content == "Original words"


def test_remediation_service_unrelated_sqlite_trigger(db_session, remediation_records):
    import sqlite3

    from app.services.interview import _delete_with_reference_guard

    original = sqlite3.IntegrityError("unrelated trigger error")
    original.sqlite_errorcode = sqlite3.SQLITE_CONSTRAINT_TRIGGER
    error = IntegrityError("synthetic statement", {}, original)
    reference_checks = iter([False, True])

    def fail():
        raise error

    with pytest.raises(IntegrityError) as caught:
        _delete_with_reference_guard(
            db_session,
            has_references=lambda: next(reference_checks),
            delete=fail,
            constraint_names={"memories_source_message_id_fkey"},
        )
    assert caught.value is error and db_session.is_active


@pytest.mark.parametrize("referenced", [True, False])
def test_r01_service_delete_identical_404(db_session, remediation_records, monkeypatch, referenced):
    import json

    from app.core.exceptions import AppException, app_exception_handler
    from app.crud import interview as interview_crud
    from app.services import interview as interview_service

    _, stranger, _, _, interview, session, message, memory = remediation_records
    if not referenced:
        db_session.delete(memory)
        db_session.commit()

    def forbidden_reference_check(*args, **kwargs):
        raise AssertionError("Unauthorized lookup must not inspect references")

    monkeypatch.setattr(interview_crud, "has_protected_references", forbidden_reference_check)
    responses = []
    for interview_id in (interview.id, uuid.uuid4()):
        with pytest.raises(AppException) as caught:
            interview_service.delete_interview(
                db_session, user_id=stranger.id, interview_id=interview_id
            )
        coroutine = app_exception_handler(None, caught.value)
        with pytest.raises(StopIteration) as returned:
            coroutine.send(None)
        response = returned.value.value
        responses.append((response.status_code, json.loads(response.body)))
    expected = (
        404,
        {
            "success": False,
            "error": {"code": "NOT_FOUND", "message": "Interview not found", "details": None},
        },
    )
    assert responses == [expected, expected]
    for record in (interview, session, message):
        assert db_session.get(type(record), record.id) is not None
    if referenced:
        assert db_session.get(type(memory), memory.id) is not None
    assert message.content == "Original words"


@pytest.mark.parametrize("referenced", [True, False])
def test_r01_api_delete_identical_404(client, db_session, referenced):
    from app.models.interview_session import InterviewSession

    owner = _register_and_login(client, "owner@example.com")
    stranger = _register_and_login(client, "stranger@example.com")
    member, message, _ = setup_member(client, owner)
    if referenced:
        assert create_memory(client, owner, member, message).status_code == 201
    source = db_session.get(InterviewMessage, uuid.UUID(message["id"]))
    interview_id = db_session.get(InterviewSession, source.session_id).interview_id
    existing = client.delete(f"/api/v1/interviews/{interview_id}", headers=stranger)
    missing = client.delete(f"/api/v1/interviews/{uuid.uuid4()}", headers=stranger)
    assert existing.status_code == missing.status_code == 404
    assert (
        existing.json()
        == missing.json()
        == {
            "success": False,
            "error": {"code": "NOT_FOUND", "message": "Interview not found", "details": None},
        }
    )
    owner_response = client.delete(f"/api/v1/interviews/{interview_id}", headers=owner)
    assert owner_response.status_code == (409 if referenced else 204)
    if referenced:
        assert owner_response.json()["error"]["code"] == "RESOURCE_IN_USE"
        assert client.get(f"/api/v1/interviews/{interview_id}", headers=owner).status_code == 200
