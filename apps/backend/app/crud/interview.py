import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.interview import Interview


def create_interview(
    db: Session,
    *,
    family_member_id: uuid.UUID,
    title: str,
    type_: str,
) -> Interview:
    interview = Interview(family_member_id=family_member_id, title=title, type=type_)
    db.add(interview)
    db.commit()
    db.refresh(interview)
    return interview


def get_interview_by_id(db: Session, *, interview_id: uuid.UUID) -> Interview | None:
    return db.get(Interview, interview_id)


def list_interviews(
    db: Session,
    *,
    family_member_id: uuid.UUID,
    offset: int,
    limit: int,
) -> tuple[list[Interview], int]:
    statement = (
        select(Interview)
        .where(Interview.family_member_id == family_member_id)
        .order_by(Interview.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    items = list(db.scalars(statement).all())

    total_statement = (
        select(func.count())
        .select_from(Interview)
        .where(Interview.family_member_id == family_member_id)
    )
    total = db.scalar(total_statement) or 0

    return items, total


def update_interview(db: Session, *, interview: Interview, values: dict[str, str]) -> Interview:
    for field, value in values.items():
        setattr(interview, field, value)
    db.commit()
    db.refresh(interview)
    return interview


def delete_interview(db: Session, *, interview: Interview) -> None:
    db.delete(interview)
    db.commit()
