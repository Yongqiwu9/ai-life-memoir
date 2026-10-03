import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.family import FamilyCreate, FamilyList, FamilyRead, FamilyUpdate
from app.services import family as family_service

router = APIRouter(prefix="/families", tags=["families"])

SessionDep = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@router.post("", response_model=FamilyRead, status_code=status.HTTP_201_CREATED)
def create_family(data: FamilyCreate, db: SessionDep, current_user: CurrentUser) -> FamilyRead:
    family = family_service.create_family(db, user_id=current_user.id, data=data)
    return FamilyRead.model_validate(family)


@router.get("", response_model=FamilyList)
def list_families(
    db: SessionDep,
    current_user: CurrentUser,
    page: Page = 1,
    page_size: PageSize = 20,
) -> FamilyList:
    items, total = family_service.list_families(
        db,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
    )
    return FamilyList(items=items, page=page, page_size=page_size, total=total)


@router.get("/{family_id}", response_model=FamilyRead)
def get_family(family_id: uuid.UUID, db: SessionDep, current_user: CurrentUser) -> FamilyRead:
    family = family_service.get_family(db, user_id=current_user.id, family_id=family_id)
    return FamilyRead.model_validate(family)


@router.patch("/{family_id}", response_model=FamilyRead)
def update_family(
    family_id: uuid.UUID,
    data: FamilyUpdate,
    db: SessionDep,
    current_user: CurrentUser,
) -> FamilyRead:
    family = family_service.update_family(
        db,
        user_id=current_user.id,
        family_id=family_id,
        data=data,
    )
    return FamilyRead.model_validate(family)


@router.delete("/{family_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_family(
    family_id: uuid.UUID,
    db: SessionDep,
    current_user: CurrentUser,
) -> Response:
    family_service.delete_family(db, user_id=current_user.id, family_id=family_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
