import uuid

from sqlalchemy.orm import Session

from app.crud import interview_message as message_crud
from app.models.interview_message import InterviewMessage
from app.schemas.interview_message import InterviewMessageCreate
from app.services import interview_session as session_service


def create_message(
    db: Session,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    data: InterviewMessageCreate,
) -> InterviewMessage:
    session_service.get_owned_session(db, user_id=user_id, session_id=session_id)
    sequence = message_crud.get_max_sequence(db, session_id=session_id) + 1
    return message_crud.create_message(
        db,
        session_id=session_id,
        role=data.role,
        content=data.content,
        sequence=sequence,
    )


def list_messages(
    db: Session,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
) -> list[InterviewMessage]:
    session_service.get_owned_session(db, user_id=user_id, session_id=session_id)
    return message_crud.list_messages(db, session_id=session_id)
