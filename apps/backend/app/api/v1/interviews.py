import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.interview import InterviewCreate, InterviewList, InterviewRead, InterviewUpdate
from app.schemas.interview_session import (
    InterviewSessionCreate,
    InterviewSessionList,
    InterviewSessionRead,
)
from app.services import interview as interview_service
from app.services import interview_session as session_service

router = APIRouter(tags=["interviews"])

SessionDep = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@router.post(
    "/family-members/{member_id}/interviews",
    response_model=InterviewRead,
    status_code=status.HTTP_201_CREATED,
)
def create_interview(
    member_id: uuid.UUID,
    data: InterviewCreate,
    db: SessionDep,
    current_user: CurrentUser,
) -> InterviewRead:
    interview = interview_service.create_interview(
        db,
        user_id=current_user.id,
        member_id=member_id,
        data=data,
    )
    return InterviewRead.model_validate(interview)


@router.get("/family-members/{member_id}/interviews", response_model=InterviewList)
def list_interviews(
    member_id: uuid.UUID,
    db: SessionDep,
    current_user: CurrentUser,
    page: Page = 1,
    page_size: PageSize = 20,
) -> InterviewList:
    items, total = interview_service.list_interviews(
        db,
        user_id=current_user.id,
        member_id=member_id,
        page=page,
        page_size=page_size,
    )
    return InterviewList(items=items, page=page, page_size=page_size, total=total)


@router.get("/interviews/{interview_id}", response_model=InterviewRead)
def get_interview(
    interview_id: uuid.UUID,
    db: SessionDep,
    current_user: CurrentUser,
) -> InterviewRead:
    interview = interview_service.get_interview(
        db,
        user_id=current_user.id,
        interview_id=interview_id,
    )
    return InterviewRead.model_validate(interview)


@router.patch("/interviews/{interview_id}", response_model=InterviewRead)
def update_interview(
    interview_id: uuid.UUID,
    data: InterviewUpdate,
    db: SessionDep,
    current_user: CurrentUser,
) -> InterviewRead:
    interview = interview_service.update_interview(
        db,
        user_id=current_user.id,
        interview_id=interview_id,
        data=data,
    )
    return InterviewRead.model_validate(interview)


@router.delete("/interviews/{interview_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_interview(
    interview_id: uuid.UUID,
    db: SessionDep,
    current_user: CurrentUser,
) -> Response:
    interview_service.delete_interview(
        db,
        user_id=current_user.id,
        interview_id=interview_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/interviews/{interview_id}/sessions",
    response_model=InterviewSessionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    interview_id: uuid.UUID,
    data: InterviewSessionCreate,
    db: SessionDep,
    current_user: CurrentUser,
) -> InterviewSessionRead:
    session = session_service.create_session(
        db,
        user_id=current_user.id,
        interview_id=interview_id,
        data=data,
    )
    return InterviewSessionRead.model_validate(session)


@router.get("/interviews/{interview_id}/sessions", response_model=InterviewSessionList)
def list_sessions(
    interview_id: uuid.UUID,
    db: SessionDep,
    current_user: CurrentUser,
) -> InterviewSessionList:
    sessions = session_service.list_sessions(
        db,
        user_id=current_user.id,
        interview_id=interview_id,
    )
    return InterviewSessionList(items=sessions, total=len(sessions))
