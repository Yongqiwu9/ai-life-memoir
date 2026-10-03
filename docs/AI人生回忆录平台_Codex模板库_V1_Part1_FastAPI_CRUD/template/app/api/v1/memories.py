from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.db.session import get_db
from app.schemas.memory import (
    MemoryCreate,
    MemoryList,
    MemoryRead,
    MemoryUpdate,
)
from app.services.memory import MemoryService

router = APIRouter(
    prefix="/memories",
    tags=["Memories"],
)


@router.post(
    "",
    response_model=MemoryRead,
    status_code=status.HTTP_201_CREATED,
)
def create_memory(
    data: MemoryCreate,
    db: Session = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> MemoryRead:
    item = MemoryService.create(
        db,
        user_id=user_id,
        data=data,
    )
    db.commit()
    return item


@router.get(
    "",
    response_model=MemoryList,
)
def list_memories(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> MemoryList:
    items, total = MemoryService.list(
        db,
        user_id=user_id,
        page=page,
        page_size=page_size,
    )

    return MemoryList(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/{memory_id}",
    response_model=MemoryRead,
)
def get_memory(
    memory_id: uuid.UUID,
    db: Session = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> MemoryRead:
    return MemoryService.get(
        db,
        user_id=user_id,
        memory_id=memory_id,
    )


@router.patch(
    "/{memory_id}",
    response_model=MemoryRead,
)
def update_memory(
    memory_id: uuid.UUID,
    data: MemoryUpdate,
    db: Session = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> MemoryRead:
    item = MemoryService.update(
        db,
        user_id=user_id,
        memory_id=memory_id,
        data=data,
    )
    db.commit()
    return item


@router.delete(
    "/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_memory(
    memory_id: uuid.UUID,
    db: Session = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> Response:
    MemoryService.delete(
        db,
        user_id=user_id,
        memory_id=memory_id,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
