import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.interview_message import InterviewMessage


def create_message(
    db: Session,
    *,
    session_id: uuid.UUID,
    role: str,
    content: str,
    sequence: int,
) -> InterviewMessage:
    message = InterviewMessage(session_id=session_id, role=role, content=content, sequence=sequence)
    db.add(message)
    db.commit()
    db.refresh(message)
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
