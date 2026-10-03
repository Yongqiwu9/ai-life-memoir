import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.interview_message import (
    InterviewMessageCreate,
    InterviewMessageList,
    InterviewMessageRead,
)
from app.schemas.interview_session import InterviewSessionRead
from app.services import interview_message as message_service
from app.services import interview_session as session_service

router = APIRouter(tags=["sessions"])

SessionDep = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("/sessions/{session_id}", response_model=InterviewSessionRead)
def get_session(
    session_id: uuid.UUID,
    db: SessionDep,
    current_user: CurrentUser,
) -> InterviewSessionRead:
    session = session_service.get_owned_session(
        db,
        user_id=current_user.id,
        session_id=session_id,
    )
    return InterviewSessionRead.model_validate(session)


@router.post(
    "/sessions/{session_id}/messages",
    response_model=InterviewMessageRead,
    status_code=status.HTTP_201_CREATED,
)
def create_message(
    session_id: uuid.UUID,
    data: InterviewMessageCreate,
    db: SessionDep,
    current_user: CurrentUser,
) -> InterviewMessageRead:
    message = message_service.create_message(
        db,
        user_id=current_user.id,
        session_id=session_id,
        data=data,
    )
    return InterviewMessageRead.model_validate(message)


@router.get("/sessions/{session_id}/messages", response_model=InterviewMessageList)
def list_messages(
    session_id: uuid.UUID,
    db: SessionDep,
    current_user: CurrentUser,
) -> InterviewMessageList:
    messages = message_service.list_messages(
        db,
        user_id=current_user.id,
        session_id=session_id,
    )
    return InterviewMessageList(items=messages, total=len(messages))
