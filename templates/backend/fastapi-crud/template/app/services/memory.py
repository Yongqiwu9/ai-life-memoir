from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.crud.memory import MemoryCRUD
from app.models.memory import Memory
from app.schemas.memory import MemoryCreate, MemoryUpdate


class MemoryService:
    @staticmethod
    def create(
        db: Session,
        *,
        user_id: uuid.UUID,
        data: MemoryCreate,
    ) -> Memory:
        return MemoryCRUD.create(
            db,
            user_id=user_id,
            data=data,
        )

    @staticmethod
    def get(
        db: Session,
        *,
        user_id: uuid.UUID,
        memory_id: uuid.UUID,
    ) -> Memory:
        item = MemoryCRUD.get_by_id(
            db,
            user_id=user_id,
            memory_id=memory_id,
        )

        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Memory not found",
            )

        return item

    @staticmethod
    def list(
        db: Session,
        *,
        user_id: uuid.UUID,
        page: int,
        page_size: int,
    ) -> tuple[list[Memory], int]:
        offset = (page - 1) * page_size

        return MemoryCRUD.list(
            db,
            user_id=user_id,
            offset=offset,
            limit=page_size,
        )

    @staticmethod
    def update(
        db: Session,
        *,
        user_id: uuid.UUID,
        memory_id: uuid.UUID,
        data: MemoryUpdate,
    ) -> Memory:
        item = MemoryService.get(
            db,
            user_id=user_id,
            memory_id=memory_id,
        )

        return MemoryCRUD.update(
            db,
            item=item,
            data=data,
        )

    @staticmethod
    def delete(
        db: Session,
        *,
        user_id: uuid.UUID,
        memory_id: uuid.UUID,
    ) -> None:
        item = MemoryService.get(
            db,
            user_id=user_id,
            memory_id=memory_id,
        )

        MemoryCRUD.delete(
            db,
            item=item,
        )
