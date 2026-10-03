import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audio_recording import AudioRecording


def create_audio(
    db: Session,
    *,
    session_id: uuid.UUID,
    original_filename: str | None,
    mime_type: str | None,
    size_bytes: int | None,
    duration_ms: int | None,
    status: str,
) -> AudioRecording:
    audio = AudioRecording(
        session_id=session_id,
        original_filename=original_filename,
        mime_type=mime_type,
        size_bytes=size_bytes,
        duration_ms=duration_ms,
        status=status,
    )
    db.add(audio)
    db.commit()
    db.refresh(audio)
    return audio


def get_audio_by_id(db: Session, *, audio_id: uuid.UUID) -> AudioRecording | None:
    return db.get(AudioRecording, audio_id)


def list_audios(db: Session, *, session_id: uuid.UUID) -> list[AudioRecording]:
    statement = (
        select(AudioRecording)
        .where(AudioRecording.session_id == session_id)
        .order_by(AudioRecording.created_at.desc())
    )
    return list(db.scalars(statement).all())
