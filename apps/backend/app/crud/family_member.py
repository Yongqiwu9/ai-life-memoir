import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.memoir import Memoir
from app.models.memory import Memory


def create_family_member(db: Session, *, family_id: uuid.UUID, name: str) -> FamilyMember:
    member = FamilyMember(family_id=family_id, name=name)
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def get_family_member(
    db: Session,
    *,
    family_id: uuid.UUID,
    member_id: uuid.UUID,
) -> FamilyMember | None:
    statement = select(FamilyMember).where(
        FamilyMember.id == member_id,
        FamilyMember.family_id == family_id,
    )
    return db.scalar(statement)


def get_family_member_by_id(db: Session, *, member_id: uuid.UUID) -> FamilyMember | None:
    return db.get(FamilyMember, member_id)


def list_family_members(
    db: Session,
    *,
    family_id: uuid.UUID,
    offset: int,
    limit: int,
) -> tuple[list[FamilyMember], int]:
    statement = (
        select(FamilyMember)
        .where(FamilyMember.family_id == family_id)
        .order_by(FamilyMember.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    items = list(db.scalars(statement).all())

    total_statement = (
        select(func.count()).select_from(FamilyMember).where(FamilyMember.family_id == family_id)
    )
    total = db.scalar(total_statement) or 0

    return items, total


def update_family_member(db: Session, *, member: FamilyMember, name: str) -> FamilyMember:
    member.name = name
    db.commit()
    db.refresh(member)
    return member


def delete_family_member(db: Session, *, member: FamilyMember) -> None:
    db.delete(member)
    db.flush()


def get_owned_memory(db: Session, *, owner_id: uuid.UUID, memory_id: uuid.UUID) -> Memory | None:
    return db.scalar(
        select(Memory)
        .join(FamilyMember, Memory.family_member_id == FamilyMember.id)
        .join(Family, FamilyMember.family_id == Family.id)
        .where(Memory.id == memory_id, Family.owner_id == owner_id)
    )


def get_owned_memoir(db: Session, *, owner_id: uuid.UUID, memoir_id: uuid.UUID) -> Memoir | None:
    return db.scalar(
        select(Memoir)
        .join(FamilyMember, Memoir.family_member_id == FamilyMember.id)
        .join(Family, FamilyMember.family_id == Family.id)
        .where(Memoir.id == memoir_id, Family.owner_id == owner_id)
        .options(selectinload(Memoir.sections))
    )


def has_protected_references(db: Session, *, member_id: uuid.UUID) -> bool:
    return (
        db.scalar(select(Memory.id).where(Memory.family_member_id == member_id).limit(1))
        is not None
        or db.scalar(select(Memoir.id).where(Memoir.family_member_id == member_id).limit(1))
        is not None
    )
