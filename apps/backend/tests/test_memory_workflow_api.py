"""Future synthetic HTTP/ASGI acceptance. Not authorized to run in the offline phase.

These tests use only the existing isolated SQLite client fixture. They exercise
actual routes/middleware rather than treating a JSON helper as HTTP evidence.
"""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.v1 import memories, memory_workflow
from app.core.memory_http import MemoryPrivacyMiddleware
from app.core.security import create_access_token, create_rights_token
from app.database.session import get_db
from app.main import app
from app.models.collaboration import CommandIdempotencyRecord, FamilyMembership
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.interview import Interview
from app.models.interview_message import InterviewMessage
from app.models.interview_session import InterviewSession
from app.models.memory import Memory
from app.models.memory_workflow import (
    ContentRevision,
    ExtractionBatch,
    MemoryCandidate,
    RevisionProposal,
)
from app.models.user import User
from app.services import memory as memory_service
from app.services import memory_extraction, memory_review
from app.services.ai_memory_client import DeterministicMockMemoryClient, UnavailableMemoryClient
from app.services.memory_integrity import (
    MemoryIntegrity,
    SyntheticKeyProvider,
    get_memory_integrity,
)
from app.services.memory_policy import (
    PURPOSES,
    DecisionStamp,
    SyntheticMemoryPolicy,
    get_memory_policy,
)

PRIVATE_TEXT = "__SYNTHETIC_PRIVATE_SOURCE__ 我记得在河边坐过。"
PRIVATE_TITLE = "__SYNTHETIC_PRIVATE_TITLE__"


def _delta_http_snapshot(db):
    from app.database.base import Base

    return {
        table.name: [
            dict(row) for row in db.execute(select(table).order_by(*table.primary_key)).mappings()
        ]
        for table in Base.metadata.sorted_tables
    }


@pytest.mark.parametrize("target", ["interview", "member", "family"])
@pytest.mark.parametrize("state", ["pending", "completed", "failed", "discarded", "cancelled"])
def test_delta_b49_old_delete_all_batch_states(client, db_session, http_graph, target, state):
    graph = http_graph
    assert db_session.connection().exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    batch = ExtractionBatch(
        requested_by_user_id=graph.owner.id,
        session_id=graph.session.id,
        family_member_id=graph.member.id,
        family_scope_id=graph.family.id,
        source_message_id=graph.message.id,
        source_scope_id=graph.message.id,
        contract_version="memory-extraction.v1",
        policy_version="synthetic-delta",
        permission_stamp={},
        provider_id="mock",
        request_fingerprint=b"b" * 32,
        idempotency_key=uuid.uuid4(),
        state=state,
        version=0,
        candidate_count=0 if state == "completed" else None,
        failure_code="AI_PROVIDER_TIMEOUT" if state == "failed" else None,
        discard_reason={"discarded": "synthetic_discard", "cancelled": "cancelled_by_owner"}.get(
            state
        ),
        finished_at=None if state == "pending" else datetime.now(UTC),
    )
    db_session.add(batch)
    db_session.commit()
    before = _delta_http_snapshot(db_session)
    path = {
        "interview": f"/api/v1/interviews/{graph.interview.id}",
        "member": f"/api/v1/families/{graph.family.id}/members/{graph.member.id}",
        "family": f"/api/v1/families/{graph.family.id}",
    }[target]
    response = client.delete(path, headers=_headers(graph.owner))
    _error(response, 409, "RESOURCE_IN_USE")
    assert all(
        value not in response.text for value in ("SQL", "Traceback", "fk_mxb", "candidate_count")
    )
    assert _delta_http_snapshot(db_session) == before
    for model in (MemoryCandidate, ContentRevision, RevisionProposal, Memory):
        assert db_session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.parametrize(
    "case",
    [
        "missing_resource_id",
        "missing_resource",
        "unsupported_resource_kind",
        "malformed_terminal_snapshot",
    ],
)
def test_delta_b57_unverifiable_existing_command_http(
    client,
    db_session,
    http_graph,
    http_capabilities,
    monkeypatch,
    case,
):
    from unittest.mock import Mock

    from app.crud import memory_workflow as workflow_crud
    from app.services import command_idempotency as commands

    graph = http_graph
    created = _manual(client, graph)
    key = uuid.uuid4()
    record = CommandIdempotencyRecord(
        actor_user_id=graph.owner.id,
        operation="memory.candidate.manual",
        idempotency_key=key,
        request_digest=b"d" * 32,
        state="completed",
        resource_kind="candidate",
        resource_id=uuid.UUID(created["candidate_id"]),
        response_status=201,
        response_body={"unregistered": "synthetic malformed metadata"},
    )
    if case == "missing_resource_id":
        record.resource_id = None
    elif case == "missing_resource":
        record.resource_id = uuid.uuid4()
    elif case == "unsupported_resource_kind":
        record.resource_kind = "unsupported_synthetic"
    db_session.add(record)
    db_session.commit()
    before = _delta_http_snapshot(db_session)
    calls_before = len(http_capabilities.provider.requests)
    blocked = Mock(side_effect=AssertionError("status query must not start/write/read source"))
    with monkeypatch.context() as guarded:
        for method in ("begin", "begin_memory"):
            guarded.setattr(commands, method, blocked)
        guarded.setattr(workflow_crud, "source_content", blocked)
        guarded.setattr(db_session, "commit", blocked)
        guarded.setattr(db_session, "flush", blocked)
        response = client.get(
            f"/api/v1/family-members/{graph.member.id}/memory-commands/memory.candidate.manual/{key}",
            headers=_headers(graph.owner),
        )
        _error(response, 503, "COMMAND_OUTCOME_UNKNOWN")
        blocked.assert_not_called()
    assert len(http_capabilities.provider.requests) == calls_before == 0
    assert _delta_http_snapshot(db_session) == before


class RecordingMockMemoryClient(DeterministicMockMemoryClient):
    def __init__(self):
        self.requests = []

    def extract(self, request):
        self.requests.append(request)
        return super().extract(request).validate_binding(request)


def _headers(user, *, key=None):
    headers = {"Authorization": "Bearer " + create_access_token(str(user.id))}
    if key is not None:
        headers["Idempotency-Key"] = str(key)
    return headers


def _payload(content=PRIVATE_TEXT):
    return {
        "title": PRIVATE_TITLE,
        "content": content,
        "time_text": None,
        "place": None,
        "emotion": None,
        "uncertainties": ["具体年份记不清了"],
    }


def _error(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == code
    if code in {"COMMAND_OUTCOME_UNKNOWN", "RESOURCE_DELETE_OUTCOME_UNKNOWN"}:
        assert body["error"]["details"]["outcome"] == "unknown"
        assert set(body["error"]["details"]) <= {
            "outcome",
            "operation",
            "command_id",
            "idempotency_key",
        }
    else:
        assert body["error"]["details"] is None
    assert PRIVATE_TEXT not in response.text
    assert PRIVATE_TITLE not in response.text
    return body


@pytest.fixture()
def http_graph(db_session):
    owner = User(email=f"b-http-owner-{uuid.uuid4().hex}@example.com", password_hash="synthetic")
    stranger = User(email=f"b-http-other-{uuid.uuid4().hex}@example.com", password_hash="synthetic")
    db_session.add_all([owner, stranger])
    db_session.flush()
    family = Family(owner_id=owner.id, name="Synthetic HTTP archive")
    db_session.add(family)
    db_session.flush()
    member = FamilyMember(family_id=family.id, name="Synthetic narrator")
    db_session.add(member)
    db_session.flush()
    interview = Interview(family_member_id=member.id, title="Synthetic", type="life_story")
    db_session.add(interview)
    db_session.flush()
    session = InterviewSession(interview_id=interview.id, status="completed")
    db_session.add(session)
    db_session.flush()
    message = InterviewMessage(
        session_id=session.id, role="user", source="text", content=PRIVATE_TEXT, sequence=1
    )
    db_session.add(message)
    db_session.commit()
    return SimpleNamespace(
        owner=owner,
        stranger=stranger,
        family=family,
        member=member,
        interview=interview,
        session=session,
        message=message,
    )


@pytest.fixture()
def http_capabilities(http_graph, monkeypatch):
    graph = http_graph
    stamp = DecisionStamp(
        operation="synthetic_fixture",
        actor_user_id=graph.owner.id,
        family_scope_id=graph.family.id,
        family_member_id=graph.member.id,
        source_scope_id=graph.message.id,
        source_generation=7,
        required_purposes=tuple(sorted(PURPOSES)),
        purpose_generations={purpose: 1 for purpose in PURPOSES},
        allow=True,
        body_available=True,
        restore_verified=True,
    )
    policy = SyntheticMemoryPolicy({graph.message.id: stamp})
    integrity = MemoryIntegrity(
        SyntheticKeyProvider({"synthetic-http": b"h" * 32}, "synthetic-http")
    )
    monkeypatch.setattr(memory_review, "get_memory_policy", lambda: policy)
    monkeypatch.setattr(memory_review, "get_memory_integrity", lambda: integrity)
    monkeypatch.setattr(memory_extraction, "get_memory_integrity", lambda: integrity)
    provider = RecordingMockMemoryClient()
    # Override the exact callable captured by the Router's Depends, not just
    # the Service factory; every HTTP request receives this same counted mock.
    saved_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_memory_policy] = lambda: policy
    app.dependency_overrides[get_memory_integrity] = lambda: integrity
    app.dependency_overrides[memory_workflow.get_memory_client] = lambda: provider
    try:
        yield SimpleNamespace(policy=policy, integrity=integrity, provider=provider)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved_overrides)


def _manual(client, graph):
    response = client.post(
        f"/api/v1/family-members/{graph.member.id}/memory-candidates/manual",
        headers=_headers(graph.owner, key=uuid.uuid4()),
        json={"source_message_id": str(graph.message.id), "payload": _payload()},
    )
    assert response.status_code == 201, response.text
    assert PRIVATE_TEXT not in response.text and PRIVATE_TITLE not in response.text
    return response.json()


def _approve(client, graph, created):
    proposal_id = created["proposal_id"]
    submitted = client.post(
        f"/api/v1/revision-proposals/{proposal_id}/submit",
        headers=_headers(graph.owner, key=uuid.uuid4()),
        json={"expected_version": 0, "expected_target_version": 0},
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["state"] == "submitted"
    approved = client.post(
        f"/api/v1/revision-proposals/{proposal_id}/approve",
        headers=_headers(graph.owner, key=uuid.uuid4()),
        json={"expected_version": 1, "expected_target_version": 0},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["state"] == "approved"
    return approved.json()


def test_http_default_capabilities_fail_closed_without_provider(
    client, db_session, http_graph, monkeypatch
):
    calls = []

    class WatchedUnavailable(UnavailableMemoryClient):
        def extract(self, request):
            calls.append(request)
            pytest.fail(
                "Unavailable capabilities must prevent extract, not dependency construction"
            )

    monkeypatch.setitem(
        app.dependency_overrides, memory_workflow.get_memory_client, WatchedUnavailable
    )
    response = client.post(
        f"/api/v1/sessions/{http_graph.session.id}/memory-extractions",
        headers=_headers(http_graph.owner, key=uuid.uuid4()),
        json={"source_message_id": str(http_graph.message.id)},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] in {
        "MEMORY_INTEGRITY_UNAVAILABLE",
        "MEMORY_PROCESSING_UNAVAILABLE",
    }
    assert db_session.scalar(select(func.count()).select_from(ExtractionBatch)) == 0
    assert db_session.scalar(select(func.count()).select_from(MemoryCandidate)) == 0
    assert calls == []


def test_http_manual_submit_approve_and_exact_memoir(
    client, db_session, http_graph, http_capabilities
):
    graph = http_graph
    created = _manual(client, graph)
    assert db_session.scalar(select(func.count()).select_from(Memory)) == 0
    approved = _approve(client, graph, created)
    memory_id = approved["memory_id"]
    revision_id = approved["memory_revision_id"]
    proposal_id = approved["proposal_id"]
    current = client.get(f"/api/v1/memories/{memory_id}", headers=_headers(graph.owner))
    assert current.status_code == 200, current.text
    assert current.json()["current_revision_id"] == revision_id
    assert current.json()["current_content"] == _payload()
    memoir = client.post(
        f"/api/v1/family-members/{graph.member.id}/memoirs",
        headers=_headers(graph.owner, key=uuid.uuid4()),
        json={
            "title": "Synthetic draft",
            "sections": [
                {
                    "memory_id": memory_id,
                    "memory_revision_id": revision_id,
                    "approval_proposal_id": proposal_id,
                }
            ],
        },
    )
    assert memoir.status_code == 201, memoir.text
    assert PRIVATE_TEXT not in memoir.text and PRIVATE_TITLE not in memoir.text
    memoir_id = memoir.json()["memoir_id"]
    sections = client.get(f"/api/v1/memoirs/{memoir_id}/sections", headers=_headers(graph.owner))
    assert sections.status_code == 200
    section = sections.json()["items"][0]
    assert section["memory_revision_id"] == revision_id
    assert section["approval_proposal_id"] == proposal_id
    assert PRIVATE_TEXT not in sections.text and PRIVATE_TITLE not in sections.text
    content = client.get(
        f"/api/v1/memoirs/{memoir_id}/sections/{section['id']}/content",
        headers=_headers(graph.owner),
    )
    assert content.status_code == 200, content.text
    assert content.json()["content"] == PRIVATE_TEXT
    assert db_session.get(InterviewMessage, graph.message.id).content == PRIVATE_TEXT


def test_http_extraction_explicit_completed_session_and_replay(
    client, db_session, http_graph, http_capabilities
):
    graph = http_graph
    key = uuid.uuid4()
    path = f"/api/v1/sessions/{graph.session.id}/memory-extractions"
    response = client.post(
        path,
        headers=_headers(graph.owner, key=key),
        json={"source_message_id": str(graph.message.id)},
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["state"] == "completed" and data["candidate_count"] == 1
    assert PRIVATE_TEXT not in response.text
    replay = client.post(
        path,
        headers=_headers(graph.owner, key=key),
        json={"source_message_id": str(graph.message.id)},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json() == data
    assert db_session.scalar(select(func.count()).select_from(Memory)) == 0
    assert db_session.scalar(select(func.count()).select_from(ExtractionBatch)) == 1
    assert len(http_capabilities.provider.requests) == 1
    request = http_capabilities.provider.requests[0]
    assert str(request.request_id) == data["batch_id"]
    assert request.source_message_id == graph.message.id
    assert request.source_text == PRIVATE_TEXT
    assert request.contract_version == "memory-extraction.v1"
    assert (
        db_session.scalar(select(ExtractionBatch.provider_id))
        == http_capabilities.provider.provider_id
    )


@pytest.mark.parametrize("operation", ["metadata", "content", "submit", "approve"])
def test_http_other_owner_and_missing_ids_are_equivalent(
    client, http_graph, http_capabilities, operation
):
    created = _manual(client, http_graph)
    patterns = {
        "metadata": ("get", "/memory-candidates/{}", created["candidate_id"], None),
        "content": ("get", "/content-revisions/{}/content", created["revision_id"], None),
        "submit": (
            "post",
            "/revision-proposals/{}/submit",
            created["proposal_id"],
            {
                "expected_version": 0,
                "expected_target_version": 0,
            },
        ),
        "approve": (
            "post",
            "/revision-proposals/{}/approve",
            created["proposal_id"],
            {
                "expected_version": 1,
                "expected_target_version": 0,
            },
        ),
    }
    method, pattern, existing_id, payload = patterns[operation]
    responses = []
    for resource_id in (existing_id, str(uuid.uuid4())):
        kwargs = {"json": payload} if payload is not None else {}
        response = getattr(client, method)(
            "/api/v1" + pattern.format(resource_id),
            headers=_headers(http_graph.stranger, key=uuid.uuid4()),
            **kwargs,
        )
        responses.append(_error(response, 404, "NOT_FOUND"))
    assert responses[0] == responses[1]


def test_http_collaborator_does_not_gain_review_or_content_access(
    client, db_session, http_graph, http_capabilities
):
    graph = http_graph
    db_session.add(
        FamilyMembership(
            family_id=graph.family.id,
            user_id=graph.stranger.id,
            role="collaborator",
            state="active",
            generation=1,
            joined_at=datetime.now(UTC),
        )
    )
    db_session.commit()
    created = _manual(client, graph)
    _error(
        client.get(
            f"/api/v1/content-revisions/{created['revision_id']}/content",
            headers=_headers(graph.stranger),
        ),
        404,
        "NOT_FOUND",
    )
    _error(
        client.post(
            f"/api/v1/revision-proposals/{created['proposal_id']}/approve",
            headers=_headers(graph.stranger, key=uuid.uuid4()),
            json={"expected_version": 0, "expected_target_version": 0},
        ),
        404,
        "NOT_FOUND",
    )


def test_http_rights_token_is_not_account_content_token(client, db_session, http_graph):
    rights_user = User(principal_kind="rights_only", email=None, password_hash=None)
    db_session.add(rights_user)
    db_session.commit()
    token = create_rights_token(
        subject=str(rights_user.id),
        principal_kind="rights_only",
        auth_generation=1,
        challenge_id=str(uuid.uuid4()),
        contact_id=str(uuid.uuid4()),
        lifetime_seconds=60,
    )
    response = client.get(
        f"/api/v1/family-members/{http_graph.member.id}/memory-candidates",
        headers={"Authorization": "Bearer " + token},
    )
    assert response.status_code == 401
    assert PRIVATE_TEXT not in response.text


def test_http_legacy_post_patch_do_not_require_new_headers(client, db_session, http_graph):
    graph = http_graph
    legacy = Memory(
        family_member_id=graph.member.id,
        source_message_id=graph.message.id,
        title=PRIVATE_TITLE,
        content=PRIVATE_TEXT,
        record_origin="legacy",
    )
    db_session.add(legacy)
    db_session.commit()
    _error(
        client.post(
            f"/api/v1/family-members/{graph.member.id}/memories",
            headers=_headers(graph.owner),
            json={
                "title": PRIVATE_TITLE,
                "content": PRIVATE_TEXT,
                "source_message_id": str(graph.message.id),
            },
        ),
        409,
        "REVISION_WORKFLOW_REQUIRED",
    )
    _error(
        client.patch(
            f"/api/v1/memories/{legacy.id}",
            headers=_headers(graph.owner),
            json={"content": "A new draft must use revisions"},
        ),
        409,
        "REVISION_WORKFLOW_REQUIRED",
    )
    header = client.get(f"/api/v1/memories/{legacy.id}", headers=_headers(graph.owner))
    assert header.status_code == 200
    assert header.json()["current_content"] is None
    assert PRIVATE_TEXT not in header.text and PRIVATE_TITLE not in header.text
    assert db_session.get(Memory, legacy.id).content == PRIVATE_TEXT
    _error(
        client.get(
            f"/api/v1/memories/{legacy.id}/legacy-snapshot",
            headers=_headers(graph.owner),
        ),
        503,
        "MEMORY_PROCESSING_UNAVAILABLE",
    )


def test_http_validation_does_not_echo_private_input(client, http_graph, http_capabilities):
    response = client.post(
        f"/api/v1/family-members/{http_graph.member.id}/memory-candidates/manual",
        headers=_headers(http_graph.owner, key=uuid.uuid4()),
        json={
            "source_message_id": str(http_graph.message.id),
            "payload": {
                **_payload(),
                "undeclared_private_field": PRIVATE_TEXT,
            },
        },
    )
    _error(response, 422, "INVALID_MEMORY_REQUEST")


@pytest.mark.parametrize("debug", [True, False])
def test_http_debug_boundary_uses_actual_route_without_private_traceback(
    db_session, http_graph, monkeypatch, caplog, debug
):
    local_app = FastAPI(debug=debug)
    local_app.add_middleware(MemoryPrivacyMiddleware)
    local_app.include_router(memories.router, prefix="/api/v1")

    def override_db():
        yield db_session

    def fail(*args, **kwargs):
        raise RuntimeError("SQL parameters and traceback: " + PRIVATE_TEXT)

    local_app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(memory_service, "get", fail)
    assert local_app.debug is debug
    with TestClient(local_app, raise_server_exceptions=False) as actual_client:
        response = actual_client.get(
            f"/api/v1/memories/{uuid.uuid4()}",
            headers=_headers(http_graph.owner),
        )
    _error(response, 500, "MEMORY_INTERNAL_ERROR")
    assert "Traceback" not in response.text and "SQL parameters" not in response.text
    assert PRIVATE_TEXT not in caplog.text


def test_http_reconciliation_unknown_does_not_enumerate_other_actor(
    client, db_session, http_graph, http_capabilities
):
    graph = http_graph
    created = _manual(client, graph)
    key = uuid.uuid4()
    path = f"/api/v1/family-members/{graph.member.id}/memory-commands/memory.candidate.manual/{key}"
    first = client.get(path, headers=_headers(graph.owner))
    _error(first, 503, "COMMAND_OUTCOME_UNKNOWN")
    db_session.add(
        CommandIdempotencyRecord(
            actor_user_id=graph.stranger.id,
            operation="memory.candidate.manual",
            idempotency_key=key,
            request_digest=b"s" * 32,
            fingerprint_scheme="memory-command.v1",
            fingerprint_key_id="synthetic-http",
            state="completed",
            resource_kind="candidate",
            resource_id=uuid.UUID(created["candidate_id"]),
            response_status=201,
            response_body={"candidate_id": created["candidate_id"]},
            completed_at=datetime.now(UTC),
        )
    )
    db_session.commit()
    second = client.get(path, headers=_headers(graph.owner))
    _error(second, 503, "COMMAND_OUTCOME_UNKNOWN")
    assert first.json() == second.json()


def test_http_exact_memoir_rejects_legacy_memory_ids_payload(client, http_graph, http_capabilities):
    response = client.post(
        f"/api/v1/family-members/{http_graph.member.id}/memoirs",
        headers=_headers(http_graph.owner, key=uuid.uuid4()),
        json={"title": PRIVATE_TITLE, "memory_ids": [str(uuid.uuid4())]},
    )
    _error(response, 422, "INVALID_MEMORY_REQUEST")


def _supp_route_matrix(graph, batch, created, approved, memoir_id, section_id):
    member, session = graph.member.id, graph.session.id
    candidate, proposal = created["candidate_id"], created["proposal_id"]
    revision, memory = created["revision_id"], approved["memory_id"]
    command = {"expected_version": 0}
    revision_data = {
        "expected_version": 0,
        "parent_revision_id": str(revision),
        "payload": _payload(),
    }
    routes = [
        (
            "extract",
            "post",
            f"/sessions/{session}/memory-extractions",
            {"source_message_id": str(graph.message.id)},
        ),
        ("batch", "get", f"/memory-extractions/{batch}", None),
        ("batches", "get", f"/sessions/{session}/memory-extractions", None),
        ("cancel", "post", f"/memory-extractions/{batch}/cancel", command),
        (
            "manual",
            "post",
            f"/family-members/{member}/memory-candidates/manual",
            {"source_message_id": str(graph.message.id), "payload": _payload()},
        ),
        ("candidates", "get", f"/family-members/{member}/memory-candidates", None),
        ("candidate_revisions", "get", f"/memory-candidates/{candidate}/revisions", None),
        ("candidate_revise", "post", f"/memory-candidates/{candidate}/revisions", revision_data),
        ("memory_revise", "post", f"/memories/{memory}/revisions", revision_data),
        ("memory_revisions", "get", f"/memories/{memory}/revisions", None),
        ("proposal", "get", f"/revision-proposals/{proposal}", None),
        ("reject", "post", f"/revision-proposals/{proposal}/reject", command),
        ("withdraw", "post", f"/revision-proposals/{proposal}/withdraw", command),
        (
            "lookup",
            "get",
            f"/family-members/{member}/memory-commands/memory.extract/{uuid.uuid4()}",
            None,
        ),
        ("memory", "get", f"/memories/{memory}", None),
        ("memory_list", "get", f"/family-members/{member}/memories", None),
        ("legacy", "get", f"/memories/{memory}/legacy-snapshot", None),
        (
            "old_post",
            "post",
            f"/family-members/{member}/memories",
            {
                "source_message_id": str(graph.message.id),
                "title": PRIVATE_TITLE,
                "content": PRIVATE_TEXT,
            },
        ),
        ("old_patch", "patch", f"/memories/{memory}", {"content": PRIVATE_TEXT}),
        (
            "memoir_create",
            "post",
            f"/family-members/{member}/memoirs",
            {
                "title": PRIVATE_TITLE,
                "sections": [
                    {
                        "memory_id": str(memory),
                        "memory_revision_id": str(approved["memory_revision_id"]),
                        "approval_proposal_id": str(proposal),
                    }
                ],
            },
        ),
        ("memoir", "get", f"/memoirs/{memoir_id}", None),
        ("sections", "get", f"/memoirs/{memoir_id}/sections", None),
        ("memoir_content", "get", f"/memoirs/{memoir_id}/content", None),
        ("section_content", "get", f"/memoirs/{memoir_id}/sections/{section_id}/content", None),
    ]
    # Existing four cross-Owner tests remain; only new principals need those routes.
    extra = [
        ("candidate", "get", f"/memory-candidates/{candidate}", None),
        ("content", "get", f"/content-revisions/{revision}/content", None),
        (
            "submit",
            "post",
            f"/revision-proposals/{proposal}/submit",
            {"expected_version": 0, "expected_target_version": 0},
        ),
        (
            "approve",
            "post",
            f"/revision-proposals/{proposal}/approve",
            {"expected_version": 1, "expected_target_version": 0},
        ),
    ]
    return routes, extra


@pytest.mark.parametrize("principal", ["other_owner", "collaborator", "rights_only", "invalid_jwt"])
def test_supp_b01_b02_all_missing_route_principal_combinations(
    client,
    db_session,
    http_graph,
    http_capabilities,
    monkeypatch,
    principal,
):
    from unittest.mock import Mock

    from app.crud import memory_workflow as workflow_crud

    graph = http_graph
    extraction = client.post(
        f"/api/v1/sessions/{graph.session.id}/memory-extractions",
        headers=_headers(graph.owner, key=uuid.uuid4()),
        json={"source_message_id": str(graph.message.id)},
    )
    assert extraction.status_code == 201
    created = _manual(client, graph)
    approved = _approve(client, graph, created)
    memoir = client.post(
        f"/api/v1/family-members/{graph.member.id}/memoirs",
        headers=_headers(graph.owner, key=uuid.uuid4()),
        json={
            "title": PRIVATE_TITLE,
            "sections": [
                {
                    "memory_id": approved["memory_id"],
                    "memory_revision_id": approved["memory_revision_id"],
                    "approval_proposal_id": approved["proposal_id"],
                }
            ],
        },
    )
    assert memoir.status_code == 201
    md = memoir.json()
    routes, extra = _supp_route_matrix(
        graph,
        extraction.json()["batch_id"],
        created,
        approved,
        md["memoir_id"],
        md["section_ids"][0],
    )
    if principal == "collaborator":
        db_session.add(
            FamilyMembership(
                family_id=graph.family.id,
                user_id=graph.stranger.id,
                role="collaborator",
                state="active",
                generation=1,
                joined_at=datetime.now(UTC),
            )
        )
        db_session.commit()
        routes += [item for item in extra if item[0] not in {"content", "approve"}]
    elif principal != "other_owner":
        routes += extra
    if principal == "rights_only":
        user = User(principal_kind="rights_only", email=None, password_hash=None)
        db_session.add(user)
        db_session.commit()
        token = create_rights_token(
            subject=str(user.id),
            principal_kind="rights_only",
            auth_generation=1,
            challenge_id=str(uuid.uuid4()),
            contact_id=str(uuid.uuid4()),
            lifetime_seconds=60,
        )
        headers = {"Authorization": "Bearer " + token}
        routes = [item for item in routes if item[0] != "candidates"]  # Already tested.
    elif principal == "invalid_jwt":
        headers = {"Authorization": "Bearer synthetic-invalid-jwt"}
    else:
        headers = _headers(graph.stranger)
    forbidden = Mock(side_effect=AssertionError("Unauthorized request cannot load body"))
    monkeypatch.setattr(workflow_crud, "source_content", forbidden)
    monkeypatch.setattr(workflow_crud, "revision_body", forbidden)
    calls_before = len(http_capabilities.provider.requests)
    for name, method, path, payload in routes:
        kwargs = {"json": payload} if payload is not None else {}
        response = getattr(client, method)(
            "/api/v1" + path, headers={**headers, "Idempotency-Key": str(uuid.uuid4())}, **kwargs
        )
        assert response.status_code == (
            401 if principal in {"rights_only", "invalid_jwt"} else 404
        ), name
        assert PRIVATE_TEXT not in response.text and PRIVATE_TITLE not in response.text
        if principal not in {"rights_only", "invalid_jwt"}:
            # Same valid request shape and same actor, with every resource UUID replaced.
            missing = path
            for identifier in (
                graph.member.id,
                graph.session.id,
                extraction.json()["batch_id"],
                created["candidate_id"],
                created["revision_id"],
                created["proposal_id"],
                approved["memory_id"],
                md["memoir_id"],
                md["section_ids"][0],
            ):
                missing = missing.replace(str(identifier), str(uuid.uuid4()))
            absent = getattr(client, method)(
                "/api/v1" + missing,
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
                **kwargs,
            )
            assert absent.status_code == 404 and absent.json() == response.json(), name
    forbidden.assert_not_called()
    assert len(http_capabilities.provider.requests) == calls_before


def test_supp_b07_saving_text_and_ending_session_never_extracts(
    client,
    db_session,
    http_graph,
    http_capabilities,
):
    from sqlalchemy import update

    graph = http_graph
    db_session.execute(
        update(InterviewSession)
        .where(InterviewSession.id == graph.session.id)
        .values(status="active")
    )
    db_session.commit()
    started = client.post(
        f"/api/v1/sessions/{graph.session.id}/agent-turns",
        headers=_headers(graph.owner, key=uuid.uuid4()),
        json={"contract_version": "interview-agent.v2", "action": "start", "expected_version": 0},
    )
    assert started.status_code == 201, started.text
    message = client.post(
        f"/api/v1/sessions/{graph.session.id}/messages",
        headers=_headers(graph.owner),
        json={
            "role": "user",
            "source": "text",
            "content": PRIVATE_TEXT + " Synthetic continuation",
        },
    )
    assert message.status_code == 201, message.text
    assert db_session.scalar(select(func.count()).select_from(ExtractionBatch)) == 0
    ended = client.post(
        f"/api/v1/sessions/{graph.session.id}/agent-turns",
        headers=_headers(graph.owner, key=uuid.uuid4()),
        json={"contract_version": "interview-agent.v2", "action": "end", "expected_version": 1},
    )
    assert ended.status_code == 201, ended.text
    db_session.expire_all()
    assert db_session.get(InterviewSession, graph.session.id).status == "completed"
    assert db_session.scalar(select(func.count()).select_from(ExtractionBatch)) == 0
    assert db_session.scalar(select(func.count()).select_from(MemoryCandidate)) == 0
    assert http_capabilities.provider.requests == []


@pytest.mark.parametrize("target", ["interview", "member", "family"])
@pytest.mark.parametrize("debug", [True, False])
@pytest.mark.parametrize("fault", ["protected_fk", "unexpected"])
def test_supp_b54_delete_debug_actual_asgi_path(
    db_session,
    http_graph,
    http_capabilities,
    monkeypatch,
    caplog,
    target,
    debug,
    fault,
):
    from unittest.mock import Mock

    from app.api.v1 import families, family_members, interviews
    from app.crud import memory_workflow as workflow_crud
    from app.services import family as family_service
    from app.services import family_member as member_service
    from app.services import interview as interview_service

    graph = http_graph
    # A real SQLite FK restriction with a deliberately stale first metadata precheck.
    created, _ = memory_review.manual_candidate(
        db_session,
        graph.owner.id,
        graph.member.id,
        memory_workflow.ManualCandidateCreate(
            source_message_id=graph.message.id, payload=_payload()
        ),
        uuid.uuid4(),
        policy=http_capabilities.policy,
        integrity=http_capabilities.integrity,
    )
    original = workflow_crud.has_workflow_references
    probes = []
    if fault == "protected_fk":

        def stale(db, **scope):
            probes.append(scope)
            return False if len(probes) == 1 else original(db, **scope)

        monkeypatch.setattr(workflow_crud, "has_workflow_references", stale)
    else:
        module, function = {
            "interview": (interview_service, "delete_interview"),
            "member": (member_service, "delete_family_member"),
            "family": (family_service, "delete_family"),
        }[target]
        monkeypatch.setattr(
            module,
            function,
            Mock(
                side_effect=RuntimeError("Synthetic SQL parameters and traceback " + PRIVATE_TEXT)
            ),
        )
    local = FastAPI(debug=debug)
    local.add_middleware(MemoryPrivacyMiddleware)
    for router in (families.router, family_members.router, interviews.router):
        local.include_router(router, prefix="/api/v1")
    local.dependency_overrides[get_db] = lambda: db_session
    path = {
        "interview": f"/interviews/{graph.interview.id}",
        "member": f"/families/{graph.family.id}/members/{graph.member.id}",
        "family": f"/families/{graph.family.id}",
    }[target]
    with TestClient(local, raise_server_exceptions=False) as actual:
        response = actual.delete("/api/v1" + path, headers=_headers(graph.owner))
    _error(
        response,
        409 if fault == "protected_fk" else 500,
        "RESOURCE_IN_USE" if fault == "protected_fk" else "MEMORY_INTERNAL_ERROR",
    )
    assert "Traceback" not in response.text and "SQL parameters" not in response.text
    assert PRIVATE_TEXT not in caplog.text
    if fault == "protected_fk":
        assert len(probes) >= 2
    db_session.expire_all()
    assert db_session.get(InterviewMessage, graph.message.id).content == PRIVATE_TEXT
    assert db_session.get(MemoryCandidate, created["candidate_id"]) is not None
    for entity in (graph.family, graph.member, graph.interview):
        assert db_session.get(type(entity), entity.id) is not None


@pytest.mark.parametrize("target", ["interview", "member", "family"])
def test_supp_b53_delete_wrong_actor_and_url_rejects_before_probe(
    client,
    http_graph,
    monkeypatch,
    target,
):
    from unittest.mock import Mock

    from app.crud import memory_workflow as workflow_crud

    graph = http_graph
    probe = Mock(side_effect=AssertionError("Scope must reject before reference probe"))
    monkeypatch.setattr(workflow_crud, "has_workflow_references", probe)
    path = {
        "interview": f"/interviews/{graph.interview.id}",
        "member": f"/families/{graph.family.id}/members/{graph.member.id}",
        "family": f"/families/{graph.family.id}",
    }[target]
    existing = client.delete("/api/v1" + path, headers=_headers(graph.stranger))
    missing = path
    for value in (graph.family.id, graph.member.id, graph.interview.id):
        missing = missing.replace(str(value), str(uuid.uuid4()))
    absent = client.delete("/api/v1" + missing, headers=_headers(graph.stranger))
    _error(existing, 404, "NOT_FOUND")
    assert absent.status_code == 404 and absent.json() == existing.json()
    if target == "member":
        wrong = client.delete(
            f"/api/v1/families/{uuid.uuid4()}/members/{graph.member.id}",
            headers=_headers(graph.owner),
        )
        _error(wrong, 404, "NOT_FOUND")
    probe.assert_not_called()


@pytest.mark.parametrize(
    "field,value",
    [("expected_version", None), ("expected_version", -1), ("expected_version", True)],
)
def test_supp_b56_malformed_versions_have_safe_http_errors(
    client,
    http_graph,
    http_capabilities,
    field,
    value,
):
    created = _manual(client, http_graph)
    response = client.post(
        f"/api/v1/revision-proposals/{created['proposal_id']}/submit",
        headers=_headers(http_graph.owner, key=uuid.uuid4()),
        json={field: value, "expected_target_version": 0},
    )
    _error(response, 422, "INVALID_MEMORY_REQUEST")
