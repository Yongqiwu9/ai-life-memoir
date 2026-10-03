import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.family_member import (
    FamilyMemberCreate,
    FamilyMemberList,
    FamilyMemberRead,
    FamilyMemberUpdate,
)
from app.services import family_member as family_member_service

router = APIRouter(prefix="/families/{family_id}/members", tags=["family-members"])

SessionDep = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@router.post("", response_model=FamilyMemberRead, status_code=status.HTTP_201_CREATED)
def create_family_member(
    family_id: uuid.UUID,
    data: FamilyMemberCreate,
    db: SessionDep,
    current_user: CurrentUser,
) -> FamilyMemberRead:
    member = family_member_service.create_family_member(
        db,
        user_id=current_user.id,
        family_id=family_id,
        data=data,
    )
    return FamilyMemberRead.model_validate(member)


@router.get("", response_model=FamilyMemberList)
def list_family_members(
    family_id: uuid.UUID,
    db: SessionDep,
    current_user: CurrentUser,
    page: Page = 1,
    page_size: PageSize = 20,
) -> FamilyMemberList:
    items, total = family_member_service.list_family_members(
        db,
        user_id=current_user.id,
        family_id=family_id,
        page=page,
        page_size=page_size,
    )
    return FamilyMemberList(items=items, page=page, page_size=page_size, total=total)


@router.get("/{member_id}", response_model=FamilyMemberRead)
def get_family_member(
    family_id: uuid.UUID,
    member_id: uuid.UUID,
    db: SessionDep,
    current_user: CurrentUser,
) -> FamilyMemberRead:
    member = family_member_service.get_family_member(
        db,
        user_id=current_user.id,
        family_id=family_id,
        member_id=member_id,
    )
    return FamilyMemberRead.model_validate(member)


@router.patch("/{member_id}", response_model=FamilyMemberRead)
def update_family_member(
    family_id: uuid.UUID,
    member_id: uuid.UUID,
    data: FamilyMemberUpdate,
    db: SessionDep,
    current_user: CurrentUser,
) -> FamilyMemberRead:
    member = family_member_service.update_family_member(
        db,
        user_id=current_user.id,
        family_id=family_id,
        member_id=member_id,
        data=data,
    )
    return FamilyMemberRead.model_validate(member)


@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_family_member(
    family_id: uuid.UUID,
    member_id: uuid.UUID,
    db: SessionDep,
    current_user: CurrentUser,
) -> Response:
    family_member_service.delete_family_member(
        db,
        user_id=current_user.id,
        family_id=family_id,
        member_id=member_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
