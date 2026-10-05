import uuid

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import delete, func, inspect, select, text
from sqlalchemy.orm import Session

from app.models.audio_recording import AudioRecording
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.interview import Interview
from app.models.interview_message import InterviewMessage
from app.models.interview_session import InterviewSession
from app.models.transcript import Transcript
from app.models.transcript_segment import TranscriptSegment
from app.models.user import User

pytestmark = pytest.mark.integration


def _create_source_chain(db_session: Session) -> tuple[Family, TranscriptSegment, InterviewMessage]:
    user = User(email="integration@example.com", password_hash="not-a-real-password")
    family = Family(owner=user, name="Integration family")
    member = FamilyMember(family=family, name="Narrator")
    interview = Interview(member=member, title="Life story", type="life_story")
    session = InterviewSession(interview=interview)
    audio = AudioRecording(session=session, status="pending")
    transcript = Transcript(audio=audio, status="completed", text="A preserved source.")
    segment = TranscriptSegment(
        transcript=transcript,
        sequence=1,
        speaker="Narrator",
        text="A preserved source.",
    )
    db_session.add_all([user, family, member, interview, session, audio, transcript, segment])
    db_session.flush()

    text_message = InterviewMessage(
        session=session,
        role="user",
        source="text",
        content="Typed source.",
        sequence=1,
    )
    transcript_message = InterviewMessage(
        session=session,
        role="user",
        source="audio_transcript",
        transcript_segment_id=segment.id,
        content="A preserved source.",
        sequence=2,
    )
    db_session.add_all([text_message, transcript_message])
    db_session.flush()
    return family, segment, transcript_message


def test_postgres_connectivity_and_migrated_schema(postgres_engine) -> None:
    table_names = set(inspect(postgres_engine).get_table_names())
    assert {
        "alembic_version",
        "users",
        "families",
        "family_members",
        "interviews",
        "interview_sessions",
        "interview_messages",
        "audio_recordings",
        "transcripts",
        "transcript_segments",
    }.issubset(table_names)

    alembic_config = Config("alembic.ini")
    expected_revision = ScriptDirectory.from_config(alembic_config).get_current_head()
    with postgres_engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            expected_revision
        )


def test_postgres_uuid_source_chain_and_foreign_key_behavior(db_session: Session) -> None:
    family, segment, transcript_message = _create_source_chain(db_session)

    assert isinstance(family.owner_id, uuid.UUID)
    assert transcript_message.source == "audio_transcript"
    assert transcript_message.transcript_segment_id == segment.id

    db_session.execute(delete(TranscriptSegment).where(TranscriptSegment.id == segment.id))
    db_session.flush()
    db_session.refresh(transcript_message)
    assert transcript_message.transcript_segment_id is None

    db_session.execute(delete(Family).where(Family.id == family.id))
    db_session.flush()

    assert db_session.scalar(select(func.count()).select_from(FamilyMember)) == 0
    assert db_session.scalar(select(func.count()).select_from(Interview)) == 0
    assert db_session.scalar(select(func.count()).select_from(InterviewSession)) == 0
    assert db_session.scalar(select(func.count()).select_from(AudioRecording)) == 0
    assert db_session.scalar(select(func.count()).select_from(Transcript)) == 0
    assert db_session.scalar(select(func.count()).select_from(InterviewMessage)) == 0
