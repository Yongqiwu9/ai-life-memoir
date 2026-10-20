from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, defer

from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.interview import Interview
from app.models.interview_agent import InterviewAgentState, InterviewAgentTurn
from app.models.interview_message import InterviewMessage
from app.models.interview_session import InterviewSession


@dataclass(frozen=True)
class MessageReference:
    id: UUID
    role: str
    source: str
    sequence: int


def owned_session(db: Session, user_id: UUID, session_id: UUID, *, lock: bool = False):
    query = (
        select(InterviewSession)
        .join(Interview, InterviewSession.interview_id == Interview.id)
        .join(FamilyMember, Interview.family_member_id == FamilyMember.id)
        .join(Family, FamilyMember.family_id == Family.id)
        .where(InterviewSession.id == session_id, Family.owner_id == user_id)
    )
    if lock:
        query = query.with_for_update(of=InterviewSession)
    return db.scalar(query.execution_options(populate_existing=True))


def get_state(db: Session, session_id: UUID):
    return db.scalar(
        select(InterviewAgentState)
        .where(InterviewAgentState.session_id == session_id)
        .execution_options(populate_existing=True)
    )


def _reference_query(session_id: UUID):
    return select(
        InterviewMessage.id,
        InterviewMessage.role,
        InterviewMessage.source,
        InterviewMessage.sequence,
    ).where(InterviewMessage.session_id == session_id)


def message_reference(db: Session, session_id: UUID, message_id: UUID):
    row = db.execute(_reference_query(session_id).where(InterviewMessage.id == message_id)).first()
    return MessageReference(*row) if row is not None else None


def latest_text_reference(db: Session, session_id: UUID):
    row = db.execute(
        _reference_query(session_id)
        .where(InterviewMessage.role == "user", InterviewMessage.source == "text")
        .order_by(InterviewMessage.sequence.desc())
        .limit(1)
    ).first()
    return MessageReference(*row) if row is not None else None


def message_content(db: Session, session_id: UUID, message_id: UUID):
    # Only the Service can call this, after current permission and closure checks.
    return db.scalar(
        select(InterviewMessage.content).where(
            InterviewMessage.session_id == session_id, InterviewMessage.id == message_id
        )
    )


def _turn_query(session_id: UUID):
    # Legacy normalized text is not needed for metadata or current-context reads.
    return (
        select(InterviewAgentTurn)
        .options(defer(InterviewAgentTurn.question_text_normalized))
        .where(InterviewAgentTurn.session_id == session_id)
        .execution_options(populate_existing=True)
    )


def find_turn(db: Session, session_id: UUID, key: UUID):
    return db.scalar(_turn_query(session_id).where(InterviewAgentTurn.idempotency_key == key))


def get_turn(db: Session, session_id: UUID, turn_id: UUID):
    return db.scalar(_turn_query(session_id).where(InterviewAgentTurn.id == turn_id))


def has_history(db: Session, session_id: UUID):
    return (
        db.scalar(
            select(InterviewAgentTurn.id)
            .where(InterviewAgentTurn.session_id == session_id)
            .limit(1)
        )
        is not None
    )


def has_legacy_turn(db: Session, session_id: UUID):
    return (
        db.scalar(
            select(InterviewAgentTurn.id)
            .where(
                InterviewAgentTurn.session_id == session_id,
                InterviewAgentTurn.contract_version == "interview-agent.v1",
            )
            .limit(1)
        )
        is not None
    )


def pending_turns(db: Session, session_id: UUID):
    return list(
        db.scalars(
            _turn_query(session_id).where(InterviewAgentTurn.execution_status == "pending")
        ).all()
    )


def question_turns(db: Session, session_id: UUID):
    return list(
        db.scalars(
            _turn_query(session_id)
            .where(
                InterviewAgentTurn.contract_version == "interview-agent.v2",
                InterviewAgentTurn.execution_status == "completed",
                InterviewAgentTurn.result_kind == "question",
            )
            .order_by(InterviewAgentTurn.resulting_version, InterviewAgentTurn.id)
        ).all()
    )


def question_turn_for_output(db: Session, session_id: UUID, output_id: UUID):
    return db.scalar(
        _turn_query(session_id).where(
            InterviewAgentTurn.contract_version == "interview-agent.v2",
            InterviewAgentTurn.execution_status == "completed",
            InterviewAgentTurn.result_kind == "question",
            InterviewAgentTurn.output_scope_id == output_id,
        )
    )


def add_flush(db: Session, record):
    db.add(record)
    db.flush()
    return record


def get_integration_profile(db: Session, session_id: UUID):
    return db.scalar(
        select(InterviewAgentState.integration_profile).where(
            InterviewAgentState.session_id == session_id
        )
    )
