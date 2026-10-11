import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.interview import Interview
from app.models.interview_message import InterviewMessage
from app.models.interview_session import InterviewSession
from app.models.memory import Memory


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
    db.flush()


def has_protected_references(db: Session, *, interview_id: uuid.UUID) -> bool:
    statement = (
        select(Memory.id)
        .join(InterviewMessage, Memory.source_message_id == InterviewMessage.id)
        .join(InterviewSession, InterviewMessage.session_id == InterviewSession.id)
        .where(InterviewSession.interview_id == interview_id)
        .limit(1)
    )
    return db.scalar(statement) is not None


def get_owned_interview(
    db: Session, *, owner_id: uuid.UUID, interview_id: uuid.UUID
) -> Interview | None:
    statement = (
        select(Interview)
        .join(FamilyMember, Interview.family_member_id == FamilyMember.id)
        .join(Family, FamilyMember.family_id == Family.id)
        .where(Interview.id == interview_id, Family.owner_id == owner_id)
    )
    return db.scalar(statement)
