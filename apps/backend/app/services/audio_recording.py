import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.crud import audio_recording as audio_crud
from app.models.audio_recording import AudioRecording
from app.schemas.audio_recording import AudioRecordingCreate
from app.services import interview_session as session_service


def get_owned_audio(db: Session, *, user_id: uuid.UUID, audio_id: uuid.UUID) -> AudioRecording:
    audio = audio_crud.get_audio_by_id(db, audio_id=audio_id)
    if audio is None:
        raise NotFoundException("Audio recording not found")
    session_service.get_owned_session(db, user_id=user_id, session_id=audio.session_id)
    return audio


def create_audio(
    db: Session,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    data: AudioRecordingCreate,
) -> AudioRecording:
    session_service.get_owned_session(db, user_id=user_id, session_id=session_id)
    return audio_crud.create_audio(
        db,
        session_id=session_id,
        original_filename=data.original_filename,
        mime_type=data.mime_type,
        size_bytes=data.size_bytes,
        duration_ms=data.duration_ms,
        status=data.status.value,
    )


def list_audios(
    db: Session,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
) -> list[AudioRecording]:
    session_service.get_owned_session(db, user_id=user_id, session_id=session_id)
    return audio_crud.list_audios(db, session_id=session_id)
