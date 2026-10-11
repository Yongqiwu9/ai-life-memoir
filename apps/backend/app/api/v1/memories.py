import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.memory import MemoryCreate, MemoryList, MemoryRead, MemoryUpdate
from app.services import memory as service

router = APIRouter(tags=["memories"])
SessionDep = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("/family-members/{member_id}/memories", response_model=MemoryRead, status_code=201)
def create(member_id: uuid.UUID, data: MemoryCreate, db: SessionDep, current_user: CurrentUser):
    return MemoryRead.model_validate(service.create(db, current_user.id, member_id, data))


@router.get("/memories/{resource_id}", response_model=MemoryRead)
def get(resource_id: uuid.UUID, db: SessionDep, current_user: CurrentUser):
    return MemoryRead.model_validate(service.get(db, current_user.id, resource_id))


@router.get("/family-members/{member_id}/memories", response_model=MemoryList)
def list_memories(
    member_id: uuid.UUID,
    db: SessionDep,
    current_user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    items, total = service.list_for_member(db, current_user.id, member_id, page, page_size)
    return MemoryList(items=items, total=total, page=page, page_size=page_size)


@router.patch("/memories/{memory_id}", response_model=MemoryRead)
def update(memory_id: uuid.UUID, data: MemoryUpdate, db: SessionDep, current_user: CurrentUser):
    return MemoryRead.model_validate(service.update(db, current_user.id, memory_id, data))
