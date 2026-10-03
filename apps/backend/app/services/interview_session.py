import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.crud import interview_session as session_crud
from app.models.interview_session import InterviewSession
from app.schemas.interview_session import InterviewSessionCreate
from app.services import interview as interview_service


def get_owned_session(
    db: Session,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
) -> InterviewSession:
    session = session_crud.get_session_by_id(db, session_id=session_id)
    if session is None:
        raise NotFoundException("Interview session not found")
    interview_service.get_owned_interview(db, user_id=user_id, interview_id=session.interview_id)
    return session


def create_session(
    db: Session,
    *,
    user_id: uuid.UUID,
    interview_id: uuid.UUID,
    data: InterviewSessionCreate,
) -> InterviewSession:
    interview_service.get_owned_interview(db, user_id=user_id, interview_id=interview_id)
    return session_crud.create_session(
        db,
        interview_id=interview_id,
        status=data.status.value,
    )


def list_sessions(
    db: Session,
    *,
    user_id: uuid.UUID,
    interview_id: uuid.UUID,
) -> list[InterviewSession]:
    interview_service.get_owned_interview(db, user_id=user_id, interview_id=interview_id)
    return session_crud.list_sessions(db, interview_id=interview_id)
