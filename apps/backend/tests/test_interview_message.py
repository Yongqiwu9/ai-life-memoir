import uuid

import pytest
from sqlalchemy import func, select, update

from app.core.exceptions import AppException
from app.models.interview_agent import InterviewAgentState
from app.models.interview_message import InterviewMessage
from app.models.interview_session import InterviewSession
from app.schemas.interview_message import InterviewMessageCreate
from app.services import interview_message as message_service
from tests.test_interview_agent import records as synthetic_records

records = synthetic_records


def _register_and_login(client, email: str, password: str = "strong-password-1"):
    register_response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert register_response.status_code == 201
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_response.status_code == 200
    return {"Authorization": f"Bearer {login_response.json()['access_token']}"}


def _setup_session(client, headers):
    family = client.post("/api/v1/families", json={"name": "My Family"}, headers=headers).json()
    member = client.post(
        f"/api/v1/families/{family['id']}/members",
        json={"name": "Member"},
        headers=headers,
    ).json()
    interview = client.post(
        f"/api/v1/family-members/{member['id']}/interviews",
        json={"title": "Interview", "type": "life_story"},
        headers=headers,
    ).json()
    session = client.post(
        f"/api/v1/interviews/{interview['id']}/sessions",
        json={},
        headers=headers,
    ).json()
    return session


def test_create_message_in_own_session(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    session = _setup_session(client, headers)

    response = client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"content": "我小时候住在上海。"},
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["role"] == "user"
    assert response.json()["content"] == "我小时候住在上海。"
    assert response.json()["sequence"] == 1


def test_list_messages_in_sequence_order(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    session = _setup_session(client, headers)
    client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"content": "第一条"},
        headers=headers,
    )
    client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"content": "第二条"},
        headers=headers,
    )

    listing = client.get(f"/api/v1/sessions/{session['id']}/messages", headers=headers).json()

    assert listing["total"] == 2
    assert [item["sequence"] for item in listing["items"]] == [1, 2]
    assert [item["content"] for item in listing["items"]] == ["第一条", "第二条"]


def test_create_message_in_other_users_session_returns_404(client) -> None:
    headers_a = _register_and_login(client, "a@example.com")
    headers_b = _register_and_login(client, "b@example.com")
    session_b = _setup_session(client, headers_b)

    response = client.post(
        f"/api/v1/sessions/{session_b['id']}/messages",
        json={"content": "Intruder"},
        headers=headers_a,
    )

    assert response.status_code == 404


def test_list_messages_of_other_users_session_returns_404(client) -> None:
    headers_a = _register_and_login(client, "a@example.com")
    headers_b = _register_and_login(client, "b@example.com")
    session_b = _setup_session(client, headers_b)

    response = client.get(f"/api/v1/sessions/{session_b['id']}/messages", headers=headers_a)

    assert response.status_code == 404


def test_reject_system_role(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    session = _setup_session(client, headers)

    response = client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"role": "system", "content": "system prompt"},
        headers=headers,
    )

    assert response.status_code == 422


def test_reject_assistant_role(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    session = _setup_session(client, headers)

    response = client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"role": "assistant", "content": "assistant reply"},
        headers=headers,
    )

    assert response.status_code == 422


def test_reject_empty_content(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    session = _setup_session(client, headers)

    response = client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"content": ""},
        headers=headers,
    )

    assert response.status_code == 422


def test_offline_text_saved_without_agent_preserves_sequence(records):
    db, users, sessions = records
    first = message_service.create_message(
        db,
        user_id=users[0].id,
        session_id=sessions[0].id,
        data=InterviewMessageCreate(content="合成原文一"),
    )
    second = message_service.create_message(
        db,
        user_id=users[0].id,
        session_id=sessions[0].id,
        data=InterviewMessageCreate(content="合成原文二"),
    )
    assert (first.sequence, second.sequence) == (1, 2)
    assert first.content == "合成原文一"
    assert db.get(InterviewAgentState, sessions[0].id) is None


def test_offline_paused_agent_still_allows_original_text(records):
    db, users, sessions = records
    state = InterviewAgentState(
        session_id=sessions[0].id,
        status="paused",
        version=2,
        generation_epoch=1,
        policy_version="synthetic-offline-policy",
    )
    db.add(state)
    db.commit()
    message = message_service.create_message(
        db,
        user_id=users[0].id,
        session_id=sessions[0].id,
        data=InterviewMessageCreate(content="暂停 AI 后继续合成讲述"),
    )
    assert message.role == "user" and message.source == "text"
    assert sessions[0].status == "active"
    assert (state.status, state.version, state.generation_epoch) == ("paused", 2, 1)


@pytest.mark.parametrize("status", ["completed", "closed", "unknown"])
def test_offline_non_active_session_rejects_original_text(records, status):
    db, users, sessions = records
    sessions[0].status = status
    db.commit()
    with pytest.raises(AppException) as caught:
        message_service.create_message(
            db,
            user_id=users[0].id,
            session_id=sessions[0].id,
            data=InterviewMessageCreate(content="合成禁止新增资料"),
        )
    assert caught.value.code == "SESSION_NOT_ACTIVE"
    assert caught.value.status_code == 409
    assert not db.in_transaction()
    assert db.scalar(select(func.count()).select_from(InterviewMessage)) == 0
    assert db.get(InterviewSession, sessions[0].id).status == status


def test_offline_lock_refresh_rejects_stale_active_session(records):
    db, users, sessions = records
    stale = sessions[0]
    db.execute(
        update(InterviewSession)
        .where(InterviewSession.id == stale.id)
        .values(status="completed")
        .execution_options(synchronize_session=False)
    )
    db.commit()
    assert stale.status == "active"
    with pytest.raises(AppException) as caught:
        message_service.create_message(
            db,
            user_id=users[0].id,
            session_id=stale.id,
            data=InterviewMessageCreate(content="缓存 active 不构成写许可"),
        )
    assert caught.value.code == "SESSION_NOT_ACTIVE"
    assert db.get(InterviewSession, stale.id).status == "completed"
    assert db.scalar(select(func.count()).select_from(InterviewMessage)) == 0


def test_offline_other_owner_and_missing_session_remain_404(records):
    db, users, sessions = records
    sessions[3].status = "completed"
    db.commit()
    for session_id in (sessions[3].id, uuid.uuid4()):
        with pytest.raises(AppException) as caught:
            message_service.create_message(
                db,
                user_id=users[0].id,
                session_id=session_id,
                data=InterviewMessageCreate(content="合成跨所有者请求"),
            )
        assert caught.value.code == "NOT_FOUND" and caught.value.status_code == 404
    assert db.scalar(select(func.count()).select_from(InterviewMessage)) == 0
