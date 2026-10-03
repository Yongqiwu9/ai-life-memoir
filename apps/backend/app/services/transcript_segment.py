import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.crud import audio_recording as audio_crud
from app.crud import transcript as transcript_crud
from app.crud import transcript_segment as segment_crud
from app.models.transcript_segment import TranscriptSegment
from app.schemas.transcript_segment import TranscriptSegmentCreate
from app.services import transcript as transcript_service


def get_owned_segment(
    db: Session,
    *,
    user_id: uuid.UUID,
    segment_id: uuid.UUID,
) -> TranscriptSegment:
    segment = segment_crud.get_segment_by_id(db, segment_id=segment_id)
    if segment is None:
        raise NotFoundException("Transcript segment not found")
    transcript_service.get_owned_transcript(
        db,
        user_id=user_id,
        transcript_id=segment.transcript_id,
    )
    return segment


def get_segment_for_session(
    db: Session,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    segment_id: uuid.UUID,
) -> TranscriptSegment:
    segment = get_owned_segment(db, user_id=user_id, segment_id=segment_id)
    transcript = transcript_crud.get_transcript_by_id(
        db,
        transcript_id=segment.transcript_id,
    )
    if transcript is None:
        raise NotFoundException("Transcript segment not found")
    audio = audio_crud.get_audio_by_id(db, audio_id=transcript.audio_recording_id)
    if audio is None or audio.session_id != session_id:
        raise NotFoundException("Transcript segment not found")
    return segment


def create_segment(
    db: Session,
    *,
    user_id: uuid.UUID,
    transcript_id: uuid.UUID,
    data: TranscriptSegmentCreate,
) -> TranscriptSegment:
    transcript_service.get_owned_transcript(db, user_id=user_id, transcript_id=transcript_id)
    sequence = (
        data.sequence
        if data.sequence is not None
        else segment_crud.get_max_sequence(db, transcript_id=transcript_id) + 1
    )
    return segment_crud.create_segment(
        db,
        transcript_id=transcript_id,
        text=data.text,
        sequence=sequence,
        speaker=data.speaker,
        start_ms=data.start_ms,
        end_ms=data.end_ms,
        confidence=data.confidence,
    )


def list_segments(
    db: Session,
    *,
    user_id: uuid.UUID,
    transcript_id: uuid.UUID,
) -> list[TranscriptSegment]:
    transcript_service.get_owned_transcript(db, user_id=user_id, transcript_id=transcript_id)
    return segment_crud.list_segments(db, transcript_id=transcript_id)
