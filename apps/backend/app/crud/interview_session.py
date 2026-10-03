import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.interview_session import InterviewSession


def create_session(db: Session, *, interview_id: uuid.UUID, status: str) -> InterviewSession:
    session = InterviewSession(interview_id=interview_id, status=status)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_session_by_id(db: Session, *, session_id: uuid.UUID) -> InterviewSession | None:
    return db.get(InterviewSession, session_id)


def list_sessions(db: Session, *, interview_id: uuid.UUID) -> list[InterviewSession]:
    statement = (
        select(InterviewSession)
        .where(InterviewSession.interview_id == interview_id)
        .order_by(InterviewSession.created_at.desc())
    )
    return list(db.scalars(statement).all())
