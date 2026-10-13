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
from app.models.memory_workflow import ExtractionBatch, MemoryCandidate
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
