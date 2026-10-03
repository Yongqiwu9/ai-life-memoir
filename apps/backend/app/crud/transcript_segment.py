import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.transcript_segment import TranscriptSegment


def create_segment(
    db: Session,
    *,
    transcript_id: uuid.UUID,
    text: str,
    sequence: int,
    speaker: str | None,
    start_ms: int | None,
    end_ms: int | None,
    confidence: float | None,
) -> TranscriptSegment:
    segment = TranscriptSegment(
        transcript_id=transcript_id,
        text=text,
        sequence=sequence,
        speaker=speaker,
        start_ms=start_ms,
        end_ms=end_ms,
        confidence=confidence,
    )
    db.add(segment)
    db.commit()
    db.refresh(segment)
    return segment


def get_segment_by_id(db: Session, *, segment_id: uuid.UUID) -> TranscriptSegment | None:
    return db.get(TranscriptSegment, segment_id)


def list_segments(db: Session, *, transcript_id: uuid.UUID) -> list[TranscriptSegment]:
    statement = (
        select(TranscriptSegment)
        .where(TranscriptSegment.transcript_id == transcript_id)
        .order_by(TranscriptSegment.sequence.asc())
    )
    return list(db.scalars(statement).all())


def get_max_sequence(db: Session, *, transcript_id: uuid.UUID) -> int:
    statement = (
        select(func.max(TranscriptSegment.sequence))
        .select_from(TranscriptSegment)
        .where(TranscriptSegment.transcript_id == transcript_id)
    )
    return db.scalar(statement) or 0
