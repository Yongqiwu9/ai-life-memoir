import uuid

import pytest
from sqlalchemy import func, select, update

from app.core.exceptions import AppException
from app.models.audio_recording import AudioRecording
from app.models.interview_message import InterviewMessage
from app.models.interview_session import InterviewSession
from app.models.transcript import Transcript
from app.models.transcript_segment import TranscriptSegment
from app.services import interview_message as message_service
from tests.test_interview_agent import records as synthetic_records

records = synthetic_records


def _register_and_login(client, email: str, password: str = "strong-password-1"):
    register = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert register.status_code == 201
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _setup_segment(client, headers):
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
    audio = client.post(
        f"/api/v1/sessions/{session['id']}/audios",
        json={},
        headers=headers,
    ).json()
    transcript = client.post(
        f"/api/v1/audios/{audio['id']}/transcripts",
        json={},
        headers=headers,
    ).json()
    segment = client.post(
        f"/api/v1/transcripts/{transcript['id']}/segments",
        json={"text": "我小时候住在上海。"},
        headers=headers,
    ).json()
    return session, segment


def test_audio_segment_links_to_user_message(client, db_session) -> None:
    headers = _register_and_login(client, "owner@example.com")
    me = client.get("/api/v1/users/me", headers=headers).json()
    session, segment = _setup_segment(client, headers)

    message = message_service.create_transcript_message(
        db_session,
        user_id=uuid.UUID(me["id"]),
        session_id=uuid.UUID(session["id"]),
        segment_id=uuid.UUID(segment["id"]),
    )

    assert message.role == "user"
    assert message.source == "audio_transcript"
    assert message.transcript_segment_id == uuid.UUID(segment["id"])
    assert message.content == segment["text"]


def test_client_cannot_create_assistant_or_ai_message(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    session, _ = _setup_segment(client, headers)

    assistant_role = client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"role": "assistant", "content": "AI reply"},
        headers=headers,
    )
    ai_source = client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"role": "user", "source": "ai_generated", "content": "AI reply"},
        headers=headers,
    )

    assert assistant_role.status_code == 422
    assert ai_source.status_code == 422


def test_text_message_does_not_require_segment(client) -> None:
    headers = _register_and_login(client, "owner@example.com")
    session, _ = _setup_segment(client, headers)

    response = client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"content": "我直接打字。"},
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["role"] == "user"
    assert response.json()["source"] == "text"
    assert response.json()["transcript_segment_id"] is None


def _offline_segment(db, session):
    audio = AudioRecording(session_id=session.id)
    db.add(audio)
    db.flush()
    transcript = Transcript(audio_recording_id=audio.id)
    db.add(transcript)
    db.flush()
    segment = TranscriptSegment(
        transcript_id=transcript.id, sequence=1, text="仅用于离线测试的合成转写"
    )
    db.add(segment)
    db.commit()
    return segment


def test_offline_segment_copy_preserves_source_link_and_original(records):
    db, users, sessions = records
    segment = _offline_segment(db, sessions[0])
    message = message_service.create_transcript_message(
        db, user_id=users[0].id, session_id=sessions[0].id, segment_id=segment.id
    )
    assert message.role == "user" and message.source == "audio_transcript"
    assert message.content == segment.text
    assert message.transcript_segment_id == segment.id
    assert message.sequence == 1
    assert db.get(TranscriptSegment, segment.id).text == "仅用于离线测试的合成转写"


def test_offline_completed_session_blocks_copy_before_source_read(records, monkeypatch):
    db, users, sessions = records
    segment = _offline_segment(db, sessions[0])
    sessions[0].status = "completed"
    db.commit()

    def forbidden_read(*args, **kwargs):
        raise AssertionError("Completed session must reject before source body read")

    monkeypatch.setattr(message_service.segment_service, "get_segment_for_session", forbidden_read)
    with pytest.raises(AppException) as caught:
        message_service.create_transcript_message(
            db, user_id=users[0].id, session_id=sessions[0].id, segment_id=segment.id
        )
    assert caught.value.code == "SESSION_NOT_ACTIVE" and caught.value.status_code == 409
    assert db.scalar(select(func.count()).select_from(InterviewMessage)) == 0
    assert db.get(TranscriptSegment, segment.id).text == "仅用于离线测试的合成转写"


def test_offline_stale_active_session_cannot_copy_segment(records):
    db, users, sessions = records
    segment = _offline_segment(db, sessions[0])
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
        message_service.create_transcript_message(
            db, user_id=users[0].id, session_id=stale.id, segment_id=segment.id
        )
    assert caught.value.code == "SESSION_NOT_ACTIVE"
    assert db.get(InterviewSession, stale.id).status == "completed"
    assert db.scalar(select(func.count()).select_from(InterviewMessage)) == 0


def test_offline_copy_cannot_cross_session_or_owner(records):
    db, users, sessions = records
    other_segment = _offline_segment(db, sessions[1])
    owner_segment = _offline_segment(db, sessions[3])
    for session_id, segment_id in (
        (sessions[0].id, other_segment.id),
        (sessions[0].id, owner_segment.id),
        (sessions[3].id, owner_segment.id),
    ):
        with pytest.raises(AppException) as caught:
            message_service.create_transcript_message(
                db, user_id=users[0].id, session_id=session_id, segment_id=segment_id
            )
        assert caught.value.code == "NOT_FOUND" and caught.value.status_code == 404
    assert db.scalar(select(func.count()).select_from(InterviewMessage)) == 0
