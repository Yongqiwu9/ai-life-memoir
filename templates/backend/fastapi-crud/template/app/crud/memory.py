from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.memory import Memory
from app.schemas.memory import MemoryCreate, MemoryUpdate


class MemoryCRUD:
    @staticmethod
    def create(
        db: Session,
        *,
        user_id: uuid.UUID,
        data: MemoryCreate,
    ) -> Memory:
        item = Memory(
            user_id=user_id,
            **data.model_dump(),
        )
        db.add(item)
        db.flush()
        db.refresh(item)
        return item

    @staticmethod
    def get_by_id(
        db: Session,
        *,
        user_id: uuid.UUID,
        memory_id: uuid.UUID,
    ) -> Memory | None:
        stmt = select(Memory).where(
            Memory.id == memory_id,
            Memory.user_id == user_id,
        )
        return db.scalar(stmt)

    @staticmethod
    def list(
        db: Session,
        *,
        user_id: uuid.UUID,
        offset: int,
        limit: int,
    ) -> tuple[list[Memory], int]:
        stmt = (
            select(Memory)
            .where(Memory.user_id == user_id)
            .order_by(Memory.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        items = list(db.scalars(stmt).all())

        count_stmt = (
            select(func.count())
            .select_from(Memory)
            .where(Memory.user_id == user_id)
        )
        total = db.scalar(count_stmt) or 0

        return items, total

    @staticmethod
    def update(
        db: Session,
        *,
        item: Memory,
        data: MemoryUpdate,
    ) -> Memory:
        values = data.model_dump(exclude_unset=True)

        for field, value in values.items():
            setattr(item, field, value)

        db.flush()
        db.refresh(item)
        return item

    @staticmethod
    def delete(
        db: Session,
        *,
        item: Memory,
    ) -> None:
        db.delete(item)
        db.flush()
