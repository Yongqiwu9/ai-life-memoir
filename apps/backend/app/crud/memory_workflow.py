"""Column-separated workflow persistence; callers own policy and transactions."""

from uuid import UUID

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session, defer

from app.models.collaboration import CommandIdempotencyRecord
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.interview import Interview
from app.models.interview_message import InterviewMessage
from app.models.interview_session import InterviewSession
from app.models.memoir import Memoir
from app.models.memory import Memory
from app.models.memory_workflow import (
    ContentRevision,
    ExtractionBatch,
    MemoryCandidate,
    RevisionProposal,
)


def owned_member(db: Session, user_id: UUID, member_id: UUID):
    return db.execute(
        select(FamilyMember.id, FamilyMember.family_id)
        .join(Family, FamilyMember.family_id == Family.id)
        .where(FamilyMember.id == member_id, Family.owner_id == user_id)
    ).first()


def owned_session(db: Session, user_id: UUID, session_id: UUID):
    return db.execute(
        select(InterviewSession.id, Interview.family_member_id, FamilyMember.family_id)
        .join(Interview, InterviewSession.interview_id == Interview.id)
        .join(FamilyMember, Interview.family_member_id == FamilyMember.id)
        .join(Family, FamilyMember.family_id == Family.id)
        .where(InterviewSession.id == session_id, Family.owner_id == user_id)
    ).first()


def source_reference(db: Session, user_id: UUID, message_id: UUID):
    return db.execute(
        select(
            InterviewMessage.id,
            InterviewMessage.session_id,
            InterviewMessage.role,
            InterviewMessage.source,
            InterviewMessage.transcript_segment_id,
            Interview.family_member_id,
            FamilyMember.family_id,
        )
        .join(InterviewSession, InterviewMessage.session_id == InterviewSession.id)
        .join(Interview, InterviewSession.interview_id == Interview.id)
        .join(FamilyMember, Interview.family_member_id == FamilyMember.id)
        .join(Family, FamilyMember.family_id == Family.id)
        .where(InterviewMessage.id == message_id, Family.owner_id == user_id)
    ).first()


def source_content(db: Session, source_id: UUID):
    return db.scalar(select(InterviewMessage.content).where(InterviewMessage.id == source_id))


def _metadata_query(model):
    query = select(model)
    if model is ContentRevision:
        query = query.options(
            defer(ContentRevision.payload),
            defer(ContentRevision.content_digest),
            defer(ContentRevision.digest_key_id),
            defer(ContentRevision.digest_scheme),
            defer(ContentRevision.input_permission_stamp),
        )
    elif model is RevisionProposal:
        query = query.options(
            defer(RevisionProposal.payload_digest),
            defer(RevisionProposal.digest_scheme),
            defer(RevisionProposal.digest_key_id),
            defer(RevisionProposal.approval_permission_stamp),
        )
    elif model is ExtractionBatch:
        query = query.options(
            defer(ExtractionBatch.permission_stamp), defer(ExtractionBatch.request_fingerprint)
        )
    return query.execution_options(populate_existing=True)


def owned_record(db: Session, model, user_id: UUID, record_id: UUID, *, lock=False):
    query = (
        _metadata_query(model)
        .join(FamilyMember, model.family_member_id == FamilyMember.id)
        .join(Family, FamilyMember.family_id == Family.id)
        .where(model.id == record_id, Family.owner_id == user_id)
    )
    if lock:
        query = query.with_for_update(of=model)
    return db.scalar(query)


def revision_body(db: Session, revision_id: UUID):
    return db.scalar(
        select(ContentRevision)
        .where(ContentRevision.id == revision_id)
        .execution_options(populate_existing=True)
    )


def revision_receipt(db: Session, revision_id: UUID):
    return db.scalar(
        select(ContentRevision.input_permission_stamp).where(ContentRevision.id == revision_id)
    )


def proposal_proof(db: Session, proposal_id: UUID):
    return db.scalar(
        select(RevisionProposal)
        .where(RevisionProposal.id == proposal_id)
        .execution_options(populate_existing=True)
    )


def batch_receipt(db: Session, batch_id: UUID):
    return db.scalar(select(ExtractionBatch.permission_stamp).where(ExtractionBatch.id == batch_id))


def list_records(db: Session, model, condition, page: int, page_size: int):
    order = (model.created_at.desc(), model.id)
    if model is ContentRevision:
        order = (ContentRevision.ordinal, ContentRevision.id)
    records = list(
        db.scalars(
            _metadata_query(model)
            .where(condition)
            .order_by(*order)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    count = db.scalar(select(func.count()).select_from(model).where(condition)) or 0
    return records, count


def candidate_references(db: Session, batch_id: UUID):
    return list(
        db.scalars(
            select(MemoryCandidate.id)
            .where(MemoryCandidate.batch_id == batch_id)
            .order_by(MemoryCandidate.batch_ordinal)
        )
    )


def revision_proposal_ids(db: Session, candidate_id: UUID):
    return list(
        db.execute(
            select(ContentRevision.id, RevisionProposal.id)
            .join(RevisionProposal, RevisionProposal.input_revision_id == ContentRevision.id)
            .where(ContentRevision.candidate_id == candidate_id)
            .order_by(ContentRevision.ordinal)
        )
    )


def find_command(db: Session, actor: UUID, operation: str, key: UUID, *, lock=False):
    query = select(CommandIdempotencyRecord).where(
        CommandIdempotencyRecord.actor_user_id == actor,
        CommandIdempotencyRecord.operation == operation,
        CommandIdempotencyRecord.idempotency_key == key,
    )
    if lock:
        query = query.with_for_update(of=CommandIdempotencyRecord)
    return db.scalar(query.execution_options(populate_existing=True))


def add_flush(db: Session, record):
    db.add(record)
    db.flush()
    return record


def has_workflow_references(db: Session, *, scope_kind: str, scope_id: UUID) -> bool:
    """Facts only: include zero-output batches and source/subject subtree unions."""
    if scope_kind == "interview":
        members = select(Interview.family_member_id).where(Interview.id == scope_id)
        sessions = select(InterviewSession.id).where(InterviewSession.interview_id == scope_id)
        # An interview guard protects only its sources, not another interview of its subject.
        subject_condition = None
    elif scope_kind == "member":
        members = select(FamilyMember.id).where(FamilyMember.id == scope_id)
        sessions = (
            select(InterviewSession.id)
            .join(Interview)
            .where(Interview.family_member_id.in_(members))
        )
        subject_condition = members
    elif scope_kind == "family":
        members = select(FamilyMember.id).where(FamilyMember.family_id == scope_id)
        sessions = (
            select(InterviewSession.id)
            .join(Interview)
            .where(Interview.family_member_id.in_(members))
        )
        subject_condition = members
    else:
        raise ValueError("Unsupported workflow reference scope")
    sources = select(InterviewMessage.id).where(InterviewMessage.session_id.in_(sessions))
    for model in (ExtractionBatch, MemoryCandidate, ContentRevision):
        condition = model.source_message_id.in_(sources)
        if model is ExtractionBatch:
            condition = or_(condition, model.session_id.in_(sessions))
        if subject_condition is not None:
            condition = or_(condition, model.family_member_id.in_(subject_condition))
        if db.scalar(select(exists().where(condition))):
            return True
    input_revisions = select(ContentRevision.id).where(
        ContentRevision.source_message_id.in_(sources)
    )
    proposal_condition = RevisionProposal.input_revision_id.in_(input_revisions)
    if subject_condition is not None:
        proposal_condition = or_(
            proposal_condition, RevisionProposal.family_member_id.in_(subject_condition)
        )
    if db.scalar(select(exists().where(proposal_condition))):
        return True
    memory_condition = Memory.source_message_id.in_(sources)
    if subject_condition is not None:
        memory_condition = or_(memory_condition, Memory.family_member_id.in_(subject_condition))
    if db.scalar(select(exists().where(memory_condition))):
        return True
    return subject_condition is not None and bool(
        db.scalar(select(exists().where(Memoir.family_member_id.in_(subject_condition))))
    )
