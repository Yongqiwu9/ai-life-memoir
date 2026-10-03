import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.family_member import FamilyMember


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
    db.commit()
