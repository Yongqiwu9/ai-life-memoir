"""Offline route/auth checks; the explicitly named HTTP tests require a safe ASGI harness."""

import inspect
import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.exc import StatementError

from app.api.v1 import interview_agent as router_module
from app.core.exceptions import (
    AGENT_SAFE_ERRORS,
    AppException,
    agent_exception_response,
    app_exception_handler,
    is_interview_agent_path,
    privacy_validation_exception_handler,
    unhandled_exception_handler,
)
from app.core.security import create_access_token
from app.dependencies.auth import get_current_user
from app.schemas.interview_agent import AgentTurnCreate
from app.services.ai_interview_client import DeterministicMockClient, UnavailableProcessingDecision
from tests.test_interview_agent import SyntheticDecision, error_body
from tests.test_interview_agent import records as records_fixture

records = records_fixture


def test_offline_router_contract_and_jwt_dependency():
    routes = {route.path: route for route in router_module.router.routes}
    assert set(routes) == {
        "/sessions/{session_id}/agent-state",
        "/sessions/{session_id}/agent-turns",
        "/sessions/{session_id}/agent-turns/{turn_id}",
    }
    assert routes["/sessions/{session_id}/agent-turns"].status_code == 201
    for route in routes.values():
        assert isinstance(route, router_module.AgentSafeRoute)
        assert any(
            dependency.call is get_current_user for dependency in route.dependant.dependencies
        )
    assert "idempotency_key" in inspect.signature(router_module.advance).parameters
    for path in (
        "/sessions/{session_id}/agent-state",
        "/sessions/{session_id}/agent-turns/{turn_id}",
    ):
        assert all(
            dependency.call
            not in {router_module.get_processing_decision, router_module.get_interview_client}
            for dependency in routes[path].dependant.dependencies
        )


def test_offline_router_metadata_does_not_need_processing(records):
    db, users, sessions = records
    state = router_module.get_state(sessions[0].id, db, users[0])
    assert state.status == "idle" and state.version == 0
    assert state.contract_version == "interview-agent.v2"


def test_offline_jwt_and_missing_auth(records):
    db, users, _ = records
    with pytest.raises(HTTPException) as caught:
        get_current_user(None, db)
    assert caught.value.status_code == 401
    token = create_access_token(subject=str(users[0].id))
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    assert get_current_user(credentials, db).id == users[0].id
    users[0].auth_generation += 1
    db.commit()
    with pytest.raises(HTTPException) as caught:
        get_current_user(credentials, db)
    assert caught.value.status_code == 401


def test_offline_route_start(records):
    db, users, sessions = records
    key = uuid.uuid4()
    data = AgentTurnCreate(
        contract_version="interview-agent.v2", action="start", expected_version=0
    )
    response = Response()
    result = router_module.advance(
        sessions[0].id,
        data,
        db,
        users[0],
        SyntheticDecision(),
        DeterministicMockClient(),
        key,
        response,
    )
    assert result.resulting_status == "listening" and result.output_message_id is None
    assert response.status_code == 201
    replay_response = Response()
    replay = router_module.advance(
        sessions[0].id,
        data,
        db,
        users[0],
        UnavailableProcessingDecision(),
        DeterministicMockClient(),
        key,
        replay_response,
    )
    assert replay_response.status_code == 200 and replay.id == result.id
    assert router_module.get_turn(sessions[0].id, result.id, db, users[0]).id == result.id
    failures = []
    for session_id, turn_id, actor in (
        (sessions[0].id, result.id, users[1]),
        (sessions[1].id, result.id, users[0]),
        (sessions[0].id, uuid.uuid4(), users[0]),
    ):
        with pytest.raises(AppException) as caught:
            router_module.get_turn(session_id, turn_id, db, actor)
        failures.append(error_body(caught.value))
    assert failures[0][0] == 404 and failures[0] == failures[1] == failures[2]
    assert set(result.model_dump()) == {
        "id",
        "session_id",
        "contract_version",
        "action",
        "execution_status",
        "result_kind",
        "result_state_contract_version",
        "resulting_version",
        "resulting_status",
        "output_message_id",
        "failure_code",
        "discard_reason",
        "created_at",
        "finished_at",
    }


@pytest.mark.parametrize("status_code", [201, 200, 202])
def test_offline_router_uses_service_status(monkeypatch, status_code):
    sentinel = object()
    arguments = []

    def with_status(*args):
        arguments.extend(args)
        return sentinel, status_code

    monkeypatch.setattr(router_module.service, "advance_with_status", with_status)
    response = Response()
    user = SimpleNamespace(id=uuid.uuid4())
    data = AgentTurnCreate(
        contract_version="interview-agent.v2", action="start", expected_version=0
    )
    session_id, key = uuid.uuid4(), uuid.uuid4()
    result = router_module.advance(
        session_id,
        data,
        None,
        user,
        UnavailableProcessingDecision(),
        DeterministicMockClient(),
        key,
        response,
    )
    assert result is sentinel and response.status_code == status_code
    assert arguments[:5] == [None, user.id, session_id, data, key]


def complete_without_io(coroutine):
    """Local wrapper unit evidence; this does not execute a real ASGI request."""
    try:
        coroutine.send(None)
    except StopIteration as completed:
        return completed.value
    else:
        coroutine.close()
        raise AssertionError("Local wrapper unexpectedly requires asynchronous I/O")


def request_for(path, *, debug=False):
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"token=synthetic-sensitive-query-marker",
            "headers": [(b"authorization", b"Bearer synthetic-sensitive-header-marker")],
            "app": FastAPI(debug=debug),
        }
    )


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/api/v1/sessions/not-a-uuid/agent-state", True),
        ("/api/v1/sessions/not-a-uuid/agent-turns", True),
        ("/api/v1/sessions/not-a-uuid/agent-turns/not-a-uuid", True),
        ("/api/v1/sessions//agent-state", False),
        ("/api/v1/sessions/x/agent-turns/", False),
        ("/api/v1/sessions/x/agent-turns/y/extra", False),
        ("/api/v1/sessions/x/messages", False),
        ("/api/v1/sessions/x/agent-turns-extra", False),
    ],
)
def test_offline_protected_path_matching_precedes_uuid_validation(path, expected):
    assert is_interview_agent_path(path) is expected
    assert is_interview_agent_path("/custom/sessions/not-a-uuid/agent-turns", "/custom")


@pytest.mark.parametrize("debug", [False, True])
@pytest.mark.parametrize(
    "stage",
    [
        "invalid_json",
        "invalid_uuid",
        "request_body",
        "dependency",
        "endpoint",
        "database",
        "provider",
        "application",
        "authentication",
        "response",
    ],
)
def test_offline_agent_route_wrapper_redacts_all_local_stages(monkeypatch, caplog, stage, debug):
    marker = "synthetic-sensitive-exception-marker"
    if stage in {"invalid_json", "invalid_uuid", "request_body"}:
        error = RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("body", "answer"),
                    "input": marker,
                    "ctx": {"error": ValueError(marker)},
                    "msg": marker,
                }
            ],
            body={"answer": marker, "token": marker},
        )
        expected_status, expected_code = 422, "INVALID_AGENT_REQUEST"
    elif stage == "response":
        error = ResponseValidationError(
            [{"type": "string_type", "loc": ("response", "body"), "input": marker}],
            body={"answer": marker},
        )
        expected_status, expected_code = 500, "AGENT_INTERNAL_ERROR"
    elif stage == "database":
        error = StatementError(marker, "SELECT synthetic_private_body", {"token": marker}, None)
        expected_status, expected_code = 500, "AGENT_INTERNAL_ERROR"
    elif stage == "application":
        error = AppException(marker, code="AI_UNAVAILABLE", details={"token": marker})
        expected_status, expected_code = 503, "AI_UNAVAILABLE"
    elif stage == "authentication":
        error = HTTPException(status_code=401, detail="Invalid token")
        expected_status, expected_code = 401, None
    else:
        error = RuntimeError(marker)
        expected_status, expected_code = 500, "AGENT_INTERNAL_ERROR"

    async def simulated_original_handler(_request):
        raise error

    monkeypatch.setattr(APIRoute, "get_route_handler", lambda _: simulated_original_handler)
    route = router_module.AgentSafeRoute(
        "/sessions/{session_id}/agent-turns", endpoint=lambda: None, methods=["POST"]
    )
    request = request_for("/api/v1/sessions/synthetic-sensitive-path/agent-turns", debug=debug)
    response = complete_without_io(route.get_route_handler()(request))
    body = json.loads(response.body)
    assert response.status_code == expected_status
    if expected_code is None:
        assert body == {"detail": "Invalid token"}
        assert response.headers["WWW-Authenticate"] == "Bearer"
    else:
        assert body["error"]["code"] == expected_code and body["error"]["details"] is None
    assert marker not in response.body.decode()
    assert "synthetic-sensitive" not in caplog.text
    assert all(record.exc_info is None and not record.args for record in caplog.records)


@pytest.mark.parametrize("debug", [False, True])
def test_offline_agent_route_wrapper_success_is_unchanged(monkeypatch, debug):
    expected = Response(content="synthetic-success", status_code=202)

    async def simulated_original_handler(_request):
        return expected

    monkeypatch.setattr(APIRoute, "get_route_handler", lambda _: simulated_original_handler)
    route = router_module.AgentSafeRoute(
        "/sessions/{session_id}/agent-turns", endpoint=lambda: None, methods=["POST"]
    )
    actual = complete_without_io(
        route.get_route_handler()(request_for("/api/v1/sessions/x/agent-turns", debug=debug))
    )
    assert actual is expected


@pytest.mark.parametrize("code", list(AGENT_SAFE_ERRORS))
def test_offline_agent_exception_codes_use_fixed_message(code, caplog):
    response = agent_exception_response(
        AppException(
            "synthetic-sensitive-message-marker",
            code=code,
            status_code=418,
            details={"token": "synthetic-sensitive-details-marker"},
        )
    )
    expected_status, expected_message = AGENT_SAFE_ERRORS[code]
    body = json.loads(response.body)
    assert response.status_code == expected_status
    assert body["error"] == {"code": code, "message": expected_message, "details": None}
    assert "synthetic-sensitive" not in response.body.decode() + caplog.text


def test_offline_unknown_application_code_is_not_echoed(caplog):
    response = agent_exception_response(
        AppException("synthetic-sensitive-marker", code="synthetic-sensitive-code")
    )
    assert response.status_code == 500
    assert "synthetic-sensitive" not in response.body.decode() + caplog.text


@pytest.mark.parametrize("detail", ["Not authenticated", "Token expired", "Invalid token"])
def test_offline_authentication_preserves_safe_detail_and_challenge(detail):
    response = agent_exception_response(
        HTTPException(
            status_code=401,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer", "X-Sensitive": "synthetic-marker"},
        )
    )
    assert response.status_code == 401 and json.loads(response.body) == {"detail": detail}
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert "X-Sensitive" not in response.headers


def test_offline_unknown_authentication_detail_is_fixed():
    response = agent_exception_response(
        HTTPException(status_code=401, detail="synthetic-sensitive-marker")
    )
    assert json.loads(response.body) == {"detail": "Not authenticated"}


def test_offline_agent_handlers_are_redacted_and_other_routes_unchanged(caplog):
    marker = "synthetic-sensitive-marker"
    agent_request = request_for("/api/v1/sessions/not-a-uuid/agent-turns")
    error = AppException(marker, code="AI_UNAVAILABLE", details={"token": marker})
    response = complete_without_io(app_exception_handler(agent_request, error))
    assert response.status_code == 503 and marker not in response.body.decode()
    unexpected = complete_without_io(
        unhandled_exception_handler(agent_request, RuntimeError(marker))
    )
    assert unexpected.status_code == 500 and marker not in unexpected.body.decode()
    assert marker not in caplog.text
    other_response = complete_without_io(
        app_exception_handler(request_for("/api/v1/unrelated"), error)
    )
    assert json.loads(other_response.body)["error"]["message"] == marker


def test_offline_validation_handler_redacts_agent_only():
    marker = "synthetic-sensitive-marker"
    error = RequestValidationError(
        [{"type": "string_type", "loc": ("body", "token"), "input": marker}]
    )
    protected = complete_without_io(
        privacy_validation_exception_handler(
            request_for("/api/v1/sessions/not-a-uuid/agent-state"), error
        )
    )
    assert protected.status_code == 422 and marker not in protected.body.decode()
    other = complete_without_io(
        privacy_validation_exception_handler(request_for("/api/v1/unrelated"), error)
    )
    assert json.loads(other.body)["detail"][0]["input"] == marker


def test_http_default_gate_and_auth(client):
    # Collect-only under current authorization; never create TestClient in offline checks.
    from unittest.mock import Mock

    from app.services.ai_interview_client import get_interview_client
    from tests.test_interview_message import _register_and_login, _setup_session

    assert client.get(f"/api/v1/sessions/{uuid.uuid4()}/agent-state").status_code == 401
    headers = _register_and_login(client, "synthetic-owner@example.invalid")
    session = _setup_session(client, headers)
    ai_client = Mock()
    overrides = dict(client.app.dependency_overrides)
    try:
        client.app.dependency_overrides[get_interview_client] = lambda: ai_client
        started = client.post(
            f"/api/v1/sessions/{session['id']}/agent-turns",
            json={
                "contract_version": "interview-agent.v2",
                "action": "start",
                "expected_version": 0,
            },
            headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert started.status_code == 201
        response = client.post(
            f"/api/v1/sessions/{session['id']}/agent-turns",
            json={
                "contract_version": "interview-agent.v2",
                "action": "request_question",
                "expected_version": 1,
            },
            headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert (
            response.status_code == 503 and response.json()["error"]["code"] == "POLICY_UNAVAILABLE"
        )
        ai_client.next_question.assert_not_called()
    finally:
        client.app.dependency_overrides.clear()
        client.app.dependency_overrides.update(overrides)


def test_http_complete_404_and_turn_response(client, db_session):
    from app.services.ai_interview_client import get_interview_client, get_processing_decision
    from tests.test_interview_message import _register_and_login, _setup_session

    owner_headers = _register_and_login(client, "synthetic-http-owner@example.invalid")
    session = _setup_session(client, owner_headers)
    headers = _register_and_login(client, "synthetic-http-stranger@example.invalid")
    responses = [
        client.post(
            f"/api/v1/sessions/{session_id}/agent-turns",
            json={
                "contract_version": "interview-agent.v2",
                "action": "start",
                "expected_version": 0,
            },
            headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        )
        for session_id in (session["id"], str(uuid.uuid4()))
    ]
    assert responses[0].status_code == responses[1].status_code == 404
    assert responses[0].json() == responses[1].json()
    overrides = dict(client.app.dependency_overrides)
    try:
        client.app.dependency_overrides[get_processing_decision] = SyntheticDecision
        client.app.dependency_overrides[get_interview_client] = DeterministicMockClient
        key = str(uuid.uuid4())
        request_headers = {**owner_headers, "Idempotency-Key": key}
        response = client.post(
            f"/api/v1/sessions/{session['id']}/agent-turns",
            json={
                "contract_version": "interview-agent.v2",
                "action": "start",
                "expected_version": 0,
            },
            headers=request_headers,
        )
        replay = client.post(
            f"/api/v1/sessions/{session['id']}/agent-turns",
            json={
                "contract_version": "interview-agent.v2",
                "action": "start",
                "expected_version": 0,
            },
            headers=request_headers,
        )
        assert response.status_code == 201 and replay.status_code == 200
        assert response.json() == replay.json()
        generated = client.post(
            f"/api/v1/sessions/{session['id']}/agent-turns",
            json={
                "contract_version": "interview-agent.v2",
                "action": "request_question",
                "expected_version": 1,
            },
            headers={**owner_headers, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert generated.status_code == 201
        messages = client.get(
            f"/api/v1/sessions/{session['id']}/messages", headers=owner_headers
        ).json()
        assert messages["items"][0]["role"] == "assistant"
        assert messages["items"][0]["source"] == "ai_generated"
    finally:
        client.app.dependency_overrides.clear()
        client.app.dependency_overrides.update(overrides)
