import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.family import Family


def create_family(db: Session, *, owner_id: uuid.UUID, name: str) -> Family:
    family = Family(owner_id=owner_id, name=name)
    db.add(family)
    db.commit()
    db.refresh(family)
    return family


def get_family(db: Session, *, owner_id: uuid.UUID, family_id: uuid.UUID) -> Family | None:
    statement = select(Family).where(Family.id == family_id, Family.owner_id == owner_id)
    return db.scalar(statement)


def list_families(
    db: Session,
    *,
    owner_id: uuid.UUID,
    offset: int,
    limit: int,
) -> tuple[list[Family], int]:
    statement = (
        select(Family)
        .where(Family.owner_id == owner_id)
        .order_by(Family.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    items = list(db.scalars(statement).all())

    total_statement = select(func.count()).select_from(Family).where(Family.owner_id == owner_id)
    total = db.scalar(total_statement) or 0

    return items, total


def update_family(db: Session, *, family: Family, name: str) -> Family:
    family.name = name
    db.commit()
    db.refresh(family)
    return family


def delete_family(db: Session, *, family: Family) -> None:
    db.delete(family)
    db.commit()
