import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.family_member import FamilyMember
from app.models.interview import Interview
from app.models.interview_participant import InterviewParticipant


def get_interview_context(db: Session, interview_id: uuid.UUID, *, lock: bool = False):
    statement = (
        select(Interview, FamilyMember)
        .join(FamilyMember, FamilyMember.id == Interview.family_member_id)
        .where(Interview.id == interview_id)
    )
    return db.execute(statement.with_for_update() if lock else statement).one_or_none()


def get_participant(db: Session, participant_id: uuid.UUID, *, lock: bool = False):
    statement = select(InterviewParticipant).where(InterviewParticipant.id == participant_id)
    return db.scalar(statement.with_for_update() if lock else statement)


def add_and_flush(db: Session, participant: InterviewParticipant):
    db.add(participant)
    db.flush()
    return participant
