import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.crud import transcript as transcript_crud
from app.models.transcript import Transcript
from app.schemas.transcript import TranscriptCreate
from app.services import audio_recording as audio_service


def get_owned_transcript(
    db: Session,
    *,
    user_id: uuid.UUID,
    transcript_id: uuid.UUID,
) -> Transcript:
    transcript = transcript_crud.get_transcript_by_id(db, transcript_id=transcript_id)
    if transcript is None:
        raise NotFoundException("Transcript not found")
    audio_service.get_owned_audio(
        db,
        user_id=user_id,
        audio_id=transcript.audio_recording_id,
    )
    return transcript


def create_transcript(
    db: Session,
    *,
    user_id: uuid.UUID,
    audio_id: uuid.UUID,
    data: TranscriptCreate,
) -> Transcript:
    audio_service.get_owned_audio(db, user_id=user_id, audio_id=audio_id)
    return transcript_crud.create_transcript(
        db,
        audio_recording_id=audio_id,
        provider=data.provider,
        model=data.model,
        language=data.language,
        status=data.status.value,
    )


def list_transcripts(
    db: Session,
    *,
    user_id: uuid.UUID,
    audio_id: uuid.UUID,
) -> list[Transcript]:
    audio_service.get_owned_audio(db, user_id=user_id, audio_id=audio_id)
    return transcript_crud.list_transcripts(db, audio_recording_id=audio_id)
