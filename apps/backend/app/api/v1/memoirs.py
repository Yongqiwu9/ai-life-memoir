import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.memoir import MemoirCreate, MemoirRead, MemoirSectionList
from app.services import memoir as service

router = APIRouter(tags=["memoirs"])
SessionDep = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("/family-members/{member_id}/memoirs", response_model=MemoirRead, status_code=201)
def create(member_id: uuid.UUID, data: MemoirCreate, db: SessionDep, current_user: CurrentUser):
    return MemoirRead.model_validate(service.create(db, current_user.id, member_id, data))


@router.get("/memoirs/{resource_id}", response_model=MemoirRead)
def get(resource_id: uuid.UUID, db: SessionDep, current_user: CurrentUser):
    return MemoirRead.model_validate(service.get(db, current_user.id, resource_id))


@router.get("/memoirs/{memoir_id}/sections", response_model=MemoirSectionList)
def sections(memoir_id: uuid.UUID, db: SessionDep, current_user: CurrentUser):
    memoir = service.get(db, current_user.id, memoir_id)
    return MemoirSectionList(items=memoir.sections, total=len(memoir.sections))
