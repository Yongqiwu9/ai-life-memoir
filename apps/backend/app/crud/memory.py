from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.interview_message import InterviewMessage
from app.models.memory import Memory


def get_message(db: Session, message_id: UUID) -> InterviewMessage | None:
    return db.get(InterviewMessage, message_id)


def get(db: Session, memory_id: UUID) -> Memory | None:
    return db.get(Memory, memory_id)


def create(db: Session, **values: object) -> Memory:
    memory = Memory(**values)
    db.add(memory)
    db.flush()
    return memory


def update(db: Session, memory: Memory, values: dict[str, object]) -> None:
    for key, value in values.items():
        setattr(memory, key, value)
    db.flush()


def list_for_member(
    db: Session, member_id: UUID, page: int, page_size: int
) -> tuple[list[Memory], int]:
    condition = Memory.family_member_id == member_id
    items = list(
        db.scalars(
            select(Memory)
            .where(condition)
            .order_by(Memory.created_at.desc(), Memory.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    total = db.scalar(select(func.count()).select_from(Memory).where(condition)) or 0
    return items, total
