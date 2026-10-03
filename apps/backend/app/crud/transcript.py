import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.transcript import Transcript


def create_transcript(
    db: Session,
    *,
    audio_recording_id: uuid.UUID,
    provider: str | None,
    model: str | None,
    language: str | None,
    status: str,
) -> Transcript:
    transcript = Transcript(
        audio_recording_id=audio_recording_id,
        provider=provider,
        model=model,
        language=language,
        status=status,
    )
    db.add(transcript)
    db.commit()
    db.refresh(transcript)
    return transcript


def get_transcript_by_id(db: Session, *, transcript_id: uuid.UUID) -> Transcript | None:
    return db.get(Transcript, transcript_id)


def list_transcripts(db: Session, *, audio_recording_id: uuid.UUID) -> list[Transcript]:
    statement = (
        select(Transcript)
        .where(Transcript.audio_recording_id == audio_recording_id)
        .order_by(Transcript.created_at.desc())
    )
    return list(db.scalars(statement).all())
