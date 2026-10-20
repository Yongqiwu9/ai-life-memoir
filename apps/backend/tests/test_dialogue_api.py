"""Specialist HTTP/ASGI cases; source only until the separate execution approval."""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event, func, select

from app.api.v1.dialogue import router
from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.dialogue_runtime import AgentEffect, AgentSource
from app.models.interview_agent import InterviewAgentState, InterviewAgentTurn
from app.models.interview_message import InterviewMessage
from app.models.interview_session import InterviewSession
from app.models.user import User
from app.schemas.dialogue import TextCreate
from app.services import dialogue as service
from app.services.dialogue_client import get_client
from app.services.dialogue_policy import get_runtime
from tests.test_dialogue import graph  # noqa: F401 - pytest fixture import


@pytest.mark.parametrize("debug", [True, False])
def test_asgi_create_start_apply_and_owner_scope(graph, debug):  # noqa: F811
    db, actor, other, session_id, runtime, client = graph
    app = FastAPI(debug=debug)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: db.get(User, actor)
    app.dependency_overrides[get_runtime] = lambda: runtime
    app.dependency_overrides[get_client] = lambda: client
    try:
        with TestClient(app) as http:
            path = f"/api/v1/sessions/{session_id}/dialogue"
            start = http.post(
                path + "/commands",
                json={"action": "start", "expected_version": 0},
                headers={"Idempotency-Key": str(uuid.uuid4())},
            )
            assert start.status_code == 202
            command_id = start.json()["id"]
            applied = http.post(
                path + f"/commands/{command_id}/apply",
                json={"expected_version": 0},
                headers={"Idempotency-Key": str(uuid.uuid4())},
            )
            assert applied.status_code == 201
            app.dependency_overrides[get_current_user] = lambda: db.get(User, other)
            denied = http.get(path + "/state")
            assert denied.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("debug", [True, False])
@pytest.mark.parametrize(
    "payload",
    [
        {"action": "response_ready", "secret": "DO_NOT_ECHO"},
        {"action": "start", "expected_version": True, "content": "DO_NOT_ECHO"},
    ],
)
def test_asgi_invalid_requests_never_echo_body(graph, debug, payload):  # noqa: F811
    db, actor, _, session_id, runtime, _ = graph
    app = FastAPI(debug=debug)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: db.get(User, actor)
    app.dependency_overrides[get_runtime] = lambda: runtime
    try:
        with TestClient(app) as http:
            result = http.post(
                f"/api/v1/sessions/{session_id}/dialogue/commands",
                json=payload,
                headers={"Idempotency-Key": str(uuid.uuid4())},
            )
    finally:
        app.dependency_overrides.clear()
    assert result.status_code == 422 and "DO_NOT_ECHO" not in result.text
    assert "traceback" not in result.text.lower()


@pytest.mark.parametrize("debug", [True, False])
@pytest.mark.parametrize("boundary", ["dependency", "endpoint", "serialization"])
def test_asgi_all_privacy_boundaries_have_fixed_errors(graph, debug, boundary, monkeypatch):  # noqa: F811
    db, actor, _, session_id, runtime, _ = graph
    from app.services import dialogue as service

    app = FastAPI(debug=debug)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: db.get(User, actor)
    app.dependency_overrides[get_runtime] = lambda: runtime

    def sensitive_failure(*_args, **_kwargs):
        raise RuntimeError("DO_NOT_ECHO_SYNTHETIC_SQL_OR_TOKEN")

    if boundary == "dependency":

        def dependency_failure():
            sensitive_failure()

        app.dependency_overrides[get_runtime] = dependency_failure
    elif boundary == "endpoint":
        monkeypatch.setattr(service, "read_state", sensitive_failure)
    else:
        monkeypatch.setattr(
            service, "read_state", lambda *_args: {"secret": "DO_NOT_ECHO_SYNTHETIC_SQL_OR_TOKEN"}
        )
    try:
        with TestClient(app) as http:
            result = http.get(f"/api/v1/sessions/{session_id}/dialogue/state")
        assert result.status_code == 500
        assert result.json()["error"]["code"] == "DIALOGUE_INTERNAL_ERROR"
        assert "DO_NOT_ECHO" not in result.text and "traceback" not in result.text.lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("debug", [True, False])
def test_asgi_malformed_json_uuid_and_missing_auth(graph, debug):  # noqa: F811
    db, actor, _, session_id, runtime, _ = graph
    app = FastAPI(debug=debug)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_runtime] = lambda: runtime
    try:
        with TestClient(app) as http:
            denied = http.get(f"/api/v1/sessions/{session_id}/dialogue/state")
            assert denied.status_code == 401
            app.dependency_overrides[get_current_user] = lambda: db.get(User, actor)
            malformed = http.post(
                f"/api/v1/sessions/{session_id}/dialogue/commands",
                content='{"secret":"DO_NOT_ECHO"',
                headers={"Idempotency-Key": str(uuid.uuid4()), "Content-Type": "application/json"},
            )
            assert malformed.status_code == 422 and "DO_NOT_ECHO" not in malformed.text
            invalid = http.get("/api/v1/sessions/DO_NOT_ECHO/dialogue/state")
            assert invalid.status_code == 422 and "DO_NOT_ECHO" not in invalid.text
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def api(graph, debug):  # noqa: F811
    db, actor, other, session_id, runtime, client = graph
    app = FastAPI(debug=debug)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: db.get(User, actor)
    app.dependency_overrides[get_runtime] = lambda: runtime
    app.dependency_overrides[get_client] = lambda: client
    try:
        with TestClient(app) as http:
            yield SimpleNamespace(
                app=app,
                http=http,
                db=db,
                actor=actor,
                other=other,
                sid=session_id,
                runtime=runtime,
                client=client,
                path=f"/api/v1/sessions/{session_id}/dialogue",
            )
    finally:
        app.dependency_overrides.clear()
        db.rollback()


def _post(api, suffix, payload, key=None, *, path=None):
    return api.http.post(
        (path or api.path) + suffix,
        json=payload,
        headers={"Idempotency-Key": str(key or uuid.uuid4())},
    )


def _state(api):
    response = api.http.get(api.path + "/state")
    assert response.status_code == 200
    return response.json()


def _command(api, action, *, apply=True):
    version = 0 if action == "start" else _state(api)["persistence_version"]
    created = _post(api, "/commands", {"action": action, "expected_version": version})
    assert created.status_code in {201, 202}
    result = created.json()
    if apply and result["execution_status"] == "queued":
        result = _post(
            api,
            f"/commands/{result['id']}/apply",
            {"expected_version": _state(api)["persistence_version"]},
        )
        assert result.status_code == 201
        result = result.json()
    return result


def _text(api, *, apply=True):
    data = {
        "content": "DO_NOT_ECHO_SYNTHETIC_NARRATIVE",
        "human_turn_id": str(uuid.uuid4()),
        "expected_version": _state(api)["persistence_version"],
    }
    key = uuid.uuid4()
    response = _post(api, "/messages", data, key)
    assert response.status_code == 202
    saved = response.json()
    if apply:
        applied = _post(
            api,
            f"/commands/{saved['id']}/apply",
            {
                "expected_version": _state(api)["persistence_version"],
            },
        )
        assert applied.status_code == 201
    return saved, data, key


def _effect(api):
    identifier = api.db.scalar(
        select(AgentEffect.id).where(
            AgentEffect.session_id == api.sid,
            AgentEffect.kind == "generate",
            AgentEffect.status == "reserved",
        )
    )
    assert identifier is not None
    api.db.rollback()
    return identifier


def _ready(api):
    _command(api, "start")
    _text(api)
    _command(api, "request_response")
    service.dispatch(api.db, api.actor, api.sid, _effect(api), api.runtime, api.client)
    state = _state(api)
    assert state["effective_status"] == "ready" and state["delivery_token"]
    return state


def _rows(api):
    """Stable metadata snapshot; no checkpoint/source body reads."""
    values = []
    for model in (InterviewMessage, InterviewAgentTurn, AgentEffect):
        values.append(api.db.scalar(select(func.count()).select_from(model)))
    values.append(
        tuple(
            tuple(row)
            for row in api.db.execute(
                select(
                    InterviewAgentState.session_id,
                    InterviewAgentState.persistence_version,
                    InterviewAgentState.stop_fence,
                    InterviewAgentState.status,
                ).order_by(InterviewAgentState.session_id)
            ).all()
        )
    )
    api.db.rollback()
    return tuple(values)


@pytest.mark.parametrize("debug", [True, False])
def test_asgi_text_command_replay_conflict_and_readback(api):
    _command(api, "start")
    _assert_text_uuid_validation(api)
    saved, data, key = _text(api, apply=False)
    before, calls = _rows(api), len(api.client.calls)
    writes = []

    def record(_conn, _cursor, statement, *_args):
        if statement.lstrip().split(None, 1)[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
            writes.append(True)

    event.listen(api.db.get_bind(), "before_cursor_execute", record)
    try:
        readback = api.http.get(api.path + f"/commands/{saved['id']}")
        assert readback.status_code == 200 and readback.json() == saved
    finally:
        event.remove(api.db.get_bind(), "before_cursor_execute", record)
    assert not writes and len(api.client.calls) == calls
    replay = _post(api, "/messages", data, key)
    assert replay.status_code == 202 and replay.json() == saved
    conflict = _post(api, "/messages", {**data, "content": "changed synthetic"}, key)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert _rows(api) == before and len(api.client.calls) == calls
    payload = {"expected_version": _state(api)["persistence_version"]}
    apply_key = uuid.uuid4()
    applied = _post(api, f"/commands/{saved['id']}/apply", payload, apply_key)
    assert applied.status_code == 201 and applied.json()["execution_status"] == "completed"
    after, calls = _rows(api), len(api.client.calls)
    replay = _post(api, f"/commands/{saved['id']}/apply", payload, apply_key)
    assert replay.status_code == 201 and replay.json() == applied.json()
    assert _rows(api) == after and len(api.client.calls) == calls
    assert api.db.scalar(select(func.count()).select_from(InterviewMessage)) == 1
    message = api.db.get(InterviewMessage, uuid.UUID(saved["message_id"]))
    assert message.role == "user" and message.content == data["content"]
    turn = api.db.get(InterviewAgentTurn, uuid.UUID(saved["id"]))
    assert turn.command_payload["human_turn_id"] == data["human_turn_id"]


def _assert_text_uuid_validation(api):
    """Keep the existing node matrix; exercise JSON and internal UUID contracts."""
    identity = uuid.uuid4()
    version = _state(api)["persistence_version"]
    data = {
        "content": "DO_NOT_ECHO_UUID_VALIDATION",
        "human_turn_id": str(identity),
        "expected_version": version,
    }
    internal = TextCreate.model_validate({**data, "human_turn_id": identity})
    decoded = TextCreate.model_validate(data)
    assert internal.human_turn_id == decoded.human_turn_id == identity
    assert isinstance(decoded.human_turn_id, uuid.UUID)
    assert TextCreate.model_config["strict"] is True
    assert TextCreate.model_config["extra"] == "forbid"
    assert TextCreate.model_config["frozen"] is True
    # bytes are not JSON values; they must also stay invalid at the internal boundary.
    for value in (identity.bytes, bytearray(identity.bytes)):
        with pytest.raises(ValidationError):
            TextCreate.model_validate({**data, "human_turn_id": value})
    before, calls = _rows(api), len(api.client.calls)
    for value in ("not-a-uuid", "", True, False, 1, 1.25, None, [], {}):
        with pytest.raises(ValidationError):
            TextCreate.model_validate({**data, "human_turn_id": value})
        response = _post(api, "/messages", {**data, "human_turn_id": value})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "DIALOGUE_INVALID_REQUEST"
        assert "DO_NOT_ECHO" not in response.text and "traceback" not in response.text.lower()
    for invalid in (
        {**data, "expected_version": True},
        {**data, "expected_version": str(version)},
        {**data, "unexpected": "DO_NOT_ECHO_EXTRA"},
    ):
        with pytest.raises(ValidationError):
            TextCreate.model_validate(invalid)
        response = _post(api, "/messages", invalid)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "DIALOGUE_INVALID_REQUEST"
        assert "DO_NOT_ECHO" not in response.text
    assert _rows(api) == before and len(api.client.calls) == calls


@pytest.mark.parametrize("debug", [True, False])
def test_asgi_manual_generation_delivery_receipts_and_replay(api):
    ready = _ready(api)
    assert sum(x.operation == "generate" for x in api.client.calls) == 1
    assert api.db.scalar(select(func.count()).select_from(InterviewMessage)) == 1
    suffix = f"/deliveries/{ready['ready_response_id']}"
    data = {"expected_version": ready["persistence_version"], "token": ready["delivery_token"]}
    key = uuid.uuid4()
    started = _post(api, suffix + "/start", data, key)
    assert started.status_code == 200
    assert started.json()["output_message_id"] and started.json()["text"]
    current = _state(api)
    assert current["effective_status"] == "delivering"
    assert current["persistence_version"] > ready["persistence_version"]
    before, calls = _rows(api), len(api.client.calls)
    replay = _post(api, suffix + "/start", data, key)
    assert replay.status_code == 200
    assert replay.json()["command"]["id"] == started.json()["command"]["id"]
    assert _rows(api) == before and len(api.client.calls) == calls
    finish_data = {**data, "expected_version": current["persistence_version"]}
    finish_key = uuid.uuid4()
    finished = _post(api, suffix + "/complete", finish_data, finish_key)
    assert finished.status_code == 200
    assert finished.json()["command"]["execution_status"] == "completed"
    before, calls = _rows(api), len(api.client.calls)
    assert _post(api, suffix + "/complete", finish_data, finish_key).json() == finished.json()
    assert _rows(api) == before and len(api.client.calls) == calls
    assert _state(api)["effective_status"] == "listening"
    assert (
        api.db.scalar(
            select(func.count())
            .select_from(InterviewMessage)
            .where(
                InterviewMessage.role == "assistant",
            )
        )
        == 1
    )


@pytest.mark.parametrize("debug", [True, False])
def test_asgi_pause_text_resume_end_lifecycle(api):
    _command(api, "start")
    prior = _state(api)
    _command(api, "pause")
    assert _state(api)["effective_status"] == "paused"
    assert _state(api)["stop_fence"] > prior["stop_fence"]
    saved, _, _ = _text(api, apply=False)
    _command(api, "resume")
    assert _state(api)["effective_status"] == "listening"
    assert (
        api.http.get(api.path + f"/commands/{saved['id']}").json()["execution_status"]
        == "completed"
    )
    assert all(x.operation != "generate" for x in api.client.calls)
    _command(api, "end")
    final = _state(api)
    assert final["effective_status"] == "ended" and final["session_status"] == "completed"
    before, calls = _rows(api), len(api.client.calls)
    rejected = _post(
        api,
        "/messages",
        {
            "content": "DO_NOT_ECHO_AFTER_END",
            "human_turn_id": str(uuid.uuid4()),
            "expected_version": final["persistence_version"],
        },
    )
    assert rejected.status_code == 409 and "DO_NOT_ECHO" not in rejected.text
    assert _rows(api) == before and len(api.client.calls) == calls


@pytest.mark.parametrize("debug", [True, False])
def test_asgi_pending_generation_late_result_after_end(api):
    _command(api, "start")
    _command(api, "request_response")
    effect = _effect(api)
    ended = []

    def stop_during_rpc(request):
        if request.operation == "generate":
            ended.append(_command(api, "end"))

    api.client.hook = stop_during_rpc
    try:
        service.dispatch(api.db, api.actor, api.sid, effect, api.runtime, api.client)
    finally:
        api.client.hook = None
    assert len(ended) == 1
    final = _state(api)
    assert final["effective_status"] == "ended" and final["ready_response_id"] is None
    assert final["session_status"] == "completed"
    assert api.db.scalar(select(func.count()).select_from(InterviewMessage)) == 0
    row = api.db.get(AgentEffect, effect, populate_existing=True)
    assert row.status == "discarded" and row.observation_code == "LATE_RESULT_IGNORED"
    assert sum(x.operation == "generate" for x in api.client.calls) == 1


def _route_request(api, route, ready, command_id, *, path=None):
    base = path or api.path
    target_id = uuid.UUID(base.split("/")[-2])
    version = api.db.get(InterviewAgentState, target_id, populate_existing=True).persistence_version
    api.db.rollback()
    if route == "state":
        return api.http.get(base + "/state")
    if route == "read":
        return api.http.get(base + f"/commands/{command_id}")
    if route == "command":
        return _post(api, "/commands", {"action": "pause", "expected_version": version}, path=base)
    if route == "message":
        return _post(
            api,
            "/messages",
            {
                "content": "DO_NOT_ECHO_FOREIGN",
                "human_turn_id": str(uuid.uuid4()),
                "expected_version": version,
            },
            path=base,
        )
    if route == "apply":
        return _post(api, f"/commands/{command_id}/apply", {"expected_version": version}, path=base)
    return _post(
        api,
        f"/deliveries/{ready['ready_response_id']}/{route}",
        {
            "expected_version": version,
            "token": ready["delivery_token"],
        },
        path=base,
    )


@pytest.mark.parametrize("debug", [True, False])
@pytest.mark.parametrize(
    "route", ["state", "command", "message", "read", "apply", "start", "complete"]
)
def test_asgi_all_routes_foreign_owner(api, route):
    ready = _ready(api)
    command_id = str(
        api.db.scalar(
            select(InterviewAgentTurn.id).where(
                InterviewAgentTurn.session_id == api.sid,
                InterviewAgentTurn.parent_turn_id.is_(None),
            )
        )
    )
    before, calls = _rows(api), len(api.client.calls)
    api.app.dependency_overrides[get_current_user] = lambda: api.db.get(User, api.other)
    denied = _route_request(api, route, ready, command_id)
    assert denied.status_code == 404
    assert "DO_NOT_ECHO" not in denied.text and ready["delivery_token"] not in denied.text
    assert _rows(api) == before and len(api.client.calls) == calls


@pytest.mark.parametrize("debug", [True, False])
@pytest.mark.parametrize("route", ["read", "apply", "start", "complete"])
def test_asgi_cross_session_resource_binding(api, route):
    ready = _ready(api)
    command_id = str(
        api.db.scalar(
            select(InterviewAgentTurn.id).where(
                InterviewAgentTurn.session_id == api.sid,
                InterviewAgentTurn.parent_turn_id.is_(None),
            )
        )
    )
    original = api.db.get(InterviewSession, api.sid)
    sibling = InterviewSession(interview_id=original.interview_id, status="active")
    api.db.add(sibling)
    api.db.commit()
    sibling_id = sibling.id
    # Initialize a second allowed synthetic scope; the real resource IDs remain
    # from the first Session. This avoids merely testing allocation denial.
    from app.services.dialogue_policy import Runtime
    from tests.test_dialogue import Allocation

    runtime = Runtime(
        Allocation(api.actor, sibling_id), api.runtime.policy, api.runtime.integrity, 1000
    )
    api.app.dependency_overrides[get_runtime] = lambda: runtime
    path = f"/api/v1/sessions/{sibling_id}/dialogue"
    started = _post(api, "/commands", {"action": "start", "expected_version": 0}, path=path)
    assert started.status_code == 202
    applied = _post(
        api, f"/commands/{started.json()['id']}/apply", {"expected_version": 0}, path=path
    )
    assert applied.status_code == 201
    before, calls = _rows(api), len(api.client.calls)
    denied = _route_request(api, route, ready, command_id, path=path)
    expected = 503 if route in {"read", "apply"} else 409
    assert denied.status_code == expected
    assert "DO_NOT_ECHO" not in denied.text and ready["delivery_token"] not in denied.text
    assert _rows(api) == before and len(api.client.calls) == calls


@pytest.mark.parametrize("debug", [True, False])
def test_asgi_restricted_source_prevents_delivery(api):
    ready = _ready(api)
    message_id = api.db.scalar(
        select(AgentSource.stable_message_id).where(AgentSource.session_id == api.sid)
    )
    api.db.rollback()
    service.restrict_source(api.db, api.actor, api.sid, message_id, api.runtime)
    before, calls = _rows(api), len(api.client.calls)
    forbidden_selects = []

    def record(_conn, _cursor, statement, *_args):
        sql = statement.lower()
        if sql.lstrip().startswith("select") and (
            "interview_messages.content" in sql or "sensitive_json" in sql
        ):
            forbidden_selects.append(True)

    event.listen(api.db.get_bind(), "before_cursor_execute", record)
    try:
        result = _route_request(api, "start", ready, "unused")
    finally:
        event.remove(api.db.get_bind(), "before_cursor_execute", record)
    assert result.status_code == 409 and result.json()["error"]["code"] == "SOURCE_UNAVAILABLE"
    assert not forbidden_selects and "DO_NOT_ECHO" not in result.text
    assert _rows(api) == before and len(api.client.calls) == calls


@pytest.mark.parametrize("debug", [True, False])
def test_asgi_expired_delivery_token(api):
    ready = _ready(api)
    api.runtime.allocation.time = ready["delivery_expires_ms"] + 1
    before, calls = _rows(api), len(api.client.calls)
    result = _route_request(api, "start", ready, "unused")
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "DIALOGUE_DELIVERY_UNAVAILABLE"
    assert ready["delivery_token"] not in result.text and "DO_NOT_ECHO" not in result.text
    assert _rows(api) == before and len(api.client.calls) == calls
