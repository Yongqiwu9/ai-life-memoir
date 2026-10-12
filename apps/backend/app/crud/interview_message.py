import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.interview_message import InterviewMessage
from app.models.interview_session import InterviewSession


def lock_session(db: Session, *, session_id: uuid.UUID) -> InterviewSession | None:
    """All Message writers use this parent row lock and a refreshed identity-map row."""
    # SQLite ignores FOR UPDATE; offline tests do not prove PostgreSQL concurrency.
    return db.scalar(
        select(InterviewSession)
        .where(InterviewSession.id == session_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def create_message_flush(
    db: Session,
    *,
    session_id: uuid.UUID,
    role: str,
    source: str,
    content: str,
    transcript_segment_id: uuid.UUID | None = None,
) -> InterviewMessage:
    # The Service locks/checks first; keep the same lock here before sequence allocation.
    # This helper only flushes. Ownership and lifecycle rules belong to the Service.
    lock_session(db, session_id=session_id)
    message = InterviewMessage(
        session_id=session_id,
        role=role,
        source=source,
        content=content,
        sequence=get_max_sequence(db, session_id=session_id) + 1,
        transcript_segment_id=transcript_segment_id,
    )
    db.add(message)
    db.flush()
    return message


def list_messages(db: Session, *, session_id: uuid.UUID) -> list[InterviewMessage]:
    statement = (
        select(InterviewMessage)
        .where(InterviewMessage.session_id == session_id)
        .order_by(InterviewMessage.sequence.asc())
    )
    return list(db.scalars(statement).all())


def get_max_sequence(db: Session, *, session_id: uuid.UUID) -> int:
    statement = (
        select(func.max(InterviewMessage.sequence))
        .select_from(InterviewMessage)
        .where(InterviewMessage.session_id == session_id)
    )
    return db.scalar(statement) or 0
