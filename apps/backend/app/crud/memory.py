from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, defer

from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.interview_message import InterviewMessage
from app.models.memory import Memory


def get_message(db: Session, message_id: UUID) -> InterviewMessage | None:
    return db.get(InterviewMessage, message_id)


def get(db: Session, memory_id: UUID) -> Memory | None:
    return db.scalar(_metadata_query().where(Memory.id == memory_id))


def _metadata_query():
    return (
        select(Memory)
        .options(
            defer(Memory.title),
            defer(Memory.content),
            defer(Memory.time_text),
            defer(Memory.place),
            defer(Memory.emotion),
        )
        .execution_options(populate_existing=True)
    )


def get_owned(db: Session, owner_id: UUID, memory_id: UUID, *, lock=False):
    statement = (
        _metadata_query()
        .join(FamilyMember, Memory.family_member_id == FamilyMember.id)
        .join(Family, FamilyMember.family_id == Family.id)
        .where(Memory.id == memory_id, Family.owner_id == owner_id)
    )
    if lock:
        statement = statement.with_for_update(of=Memory)
    return db.scalar(statement)


def legacy_body(db: Session, memory_id: UUID):
    return db.execute(
        select(
            Memory.title,
            Memory.content,
            Memory.time_text,
            Memory.place,
            Memory.emotion,
        ).where(Memory.id == memory_id)
    ).first()


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
            _metadata_query()
            .where(condition)
            .order_by(Memory.created_at.desc(), Memory.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    total = db.scalar(select(func.count()).select_from(Memory).where(condition)) or 0
    return items, total
