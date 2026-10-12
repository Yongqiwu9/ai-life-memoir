import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import AppException, NotFoundException
from app.crud import interview_message as message_crud
from app.models.interview_message import InterviewMessage
from app.schemas.interview_message import InterviewMessageCreate
from app.services import interview_session as session_service
from app.services import transcript_segment as segment_service


def _lock_writable_session(db: Session, *, user_id: uuid.UUID, session_id: uuid.UUID) -> None:
    locked = message_crud.lock_session(db, session_id=session_id)
    if locked is None:
        raise NotFoundException("Interview session not found")
    session_service.get_owned_session(db, user_id=user_id, session_id=session_id)
    if locked.status != "active":
        raise AppException(
            "Interview session is not active", code="SESSION_NOT_ACTIVE", status_code=409
        )


def create_message(
    db: Session,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    data: InterviewMessageCreate,
) -> InterviewMessage:
    try:
        _lock_writable_session(db, user_id=user_id, session_id=session_id)
        message = message_crud.create_message_flush(
            db, session_id=session_id, role=data.role, source=data.source, content=data.content
        )
        db.commit()
        db.refresh(message)
        return message
    except Exception:
        db.rollback()
        raise


def list_messages(
    db: Session,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
) -> list[InterviewMessage]:
    session_service.get_owned_session(db, user_id=user_id, session_id=session_id)
    return message_crud.list_messages(db, session_id=session_id)


def create_transcript_message(
    db: Session,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    segment_id: uuid.UUID,
) -> InterviewMessage:
    try:
        _lock_writable_session(db, user_id=user_id, session_id=session_id)
        segment = segment_service.get_segment_for_session(
            db,
            user_id=user_id,
            session_id=session_id,
            segment_id=segment_id,
        )
        message = message_crud.create_message_flush(
            db,
            session_id=session_id,
            role="user",
            source="audio_transcript",
            content=segment.text,
            transcript_segment_id=segment.id,
        )
        db.commit()
        db.refresh(message)
        return message
    except Exception:
        db.rollback()
        raise
