from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.orm import Session

from app.core.memory_http import MemorySafeRoute
from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.memoir import (
    MemoirContent,
    MemoirCreate,
    MemoirRead,
    MemoirSectionContent,
    MemoirSectionList,
)
from app.schemas.memory_workflow import MemoirCreated, ProcessingCommandResult
from app.services import memoir as service
from app.services.memory_integrity import MemoryIntegrity, get_memory_integrity
from app.services.memory_policy import MemoryPolicy, get_memory_policy

router = APIRouter(tags=["memoirs"], route_class=MemorySafeRoute)
Db = Annotated[Session, Depends(get_db)]
Actor = Annotated[User, Depends(get_current_user)]
Policy = Annotated[MemoryPolicy, Depends(get_memory_policy)]
Integrity = Annotated[MemoryIntegrity, Depends(get_memory_integrity)]


@router.post(
    "/family-members/{member_id}/memoirs",
    status_code=201,
    response_model=MemoirCreated | ProcessingCommandResult,
    response_model_exclude_unset=True,
)
def create(
    member_id: UUID,
    data: MemoirCreate,
    db: Db,
    actor: Actor,
    policy: Policy,
    integrity: Integrity,
    response: Response,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
):
    result, response.status_code = service.create(
        db, actor.id, member_id, data, idempotency_key, policy=policy, integrity=integrity
    )
    return result


@router.get("/memoirs/{resource_id}", response_model=MemoirRead)
def get(resource_id: UUID, db: Db, actor: Actor):
    return service.get(db, actor.id, resource_id)


@router.get("/memoirs/{memoir_id}/sections", response_model=MemoirSectionList)
def sections(
    memoir_id: UUID,
    db: Db,
    actor: Actor,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    items, total = service.list_sections(db, actor.id, memoir_id, page, page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/memoirs/{memoir_id}/content", response_model=MemoirContent)
def content(memoir_id: UUID, db: Db, actor: Actor, policy: Policy, integrity: Integrity):
    return service.content(db, actor.id, memoir_id, policy=policy, integrity=integrity)


@router.get(
    "/memoirs/{memoir_id}/sections/{section_id}/content", response_model=MemoirSectionContent
)
def section_content(
    memoir_id: UUID, section_id: UUID, db: Db, actor: Actor, policy: Policy, integrity: Integrity
):
    return service.section_content(
        db, actor.id, memoir_id, section_id, policy=policy, integrity=integrity
    )
