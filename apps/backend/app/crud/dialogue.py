"""Flush-only, metadata-first queries. Authorization and lifecycle live in Service."""

from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, defer

from app.models.dialogue_runtime import AgentCheckpoint, AgentDependency, AgentEffect, AgentSource
from app.models.interview_agent import InterviewAgentState, InterviewAgentTurn
from app.models.interview_message import InterviewMessage


def state(db: Session, session_id: UUID, *, lock=False):
    query = select(InterviewAgentState).where(InterviewAgentState.session_id == session_id)
    if lock:
        query = query.with_for_update()
    return db.scalar(query.execution_options(populate_existing=True))


def turn(db, session_id, *, key=None, turn_id=None):
    query = select(InterviewAgentTurn).where(InterviewAgentTurn.session_id == session_id)
    query = (
        query.where(InterviewAgentTurn.idempotency_key == key)
        if key is not None
        else query.where(InterviewAgentTurn.id == turn_id)
    )
    return db.scalar(query.execution_options(populate_existing=True))


def turns(db, session_id):
    return list(
        db.scalars(
            select(InterviewAgentTurn)
            .where(InterviewAgentTurn.session_id == session_id)
            .order_by(InterviewAgentTurn.command_order)
        )
    )


def checkpoint(db, session_id):
    return db.scalar(
        select(AgentCheckpoint)
        .options(defer(AgentCheckpoint.sensitive_json))
        .where(AgentCheckpoint.session_id == session_id)
        .execution_options(populate_existing=True)
    )


def sensitive(db, session_id):
    return db.scalar(
        select(AgentCheckpoint.sensitive_json).where(AgentCheckpoint.session_id == session_id)
    )


def purge_checkpoint(db, session_id):
    db.execute(
        update(AgentCheckpoint)
        .where(AgentCheckpoint.session_id == session_id)
        .values(sensitive_json=None, content_status="purged")
    )


def sources(db, session_id):
    return list(
        db.scalars(
            select(AgentSource)
            .where(AgentSource.session_id == session_id)
            .order_by(AgentSource.message_sequence)
        )
    )


def message_metadata(db, session_id, message_id):
    return db.execute(
        select(
            InterviewMessage.id,
            InterviewMessage.role,
            InterviewMessage.source,
            InterviewMessage.sequence,
        ).where(InterviewMessage.session_id == session_id, InterviewMessage.id == message_id)
    ).one_or_none()


def message_body(db, session_id, message_id):
    return db.scalar(
        select(InterviewMessage.content).where(
            InterviewMessage.session_id == session_id, InterviewMessage.id == message_id
        )
    )


def effects(db, session_id):
    return list(db.scalars(select(AgentEffect).where(AgentEffect.session_id == session_id)))


def replace_checkpoint_edges(db, session_id, refs):
    db.execute(
        delete(AgentDependency).where(
            AgentDependency.session_id == session_id, AgentDependency.owner_kind == "checkpoint"
        )
    )
    for source in dict.fromkeys(ref.entity_id for ref in refs):
        db.add(
            AgentDependency(
                session_id=session_id,
                source_message_id=source,
                owner_kind="checkpoint",
                checkpoint_session_id=session_id,
            )
        )


def add_flush(db, item):
    db.add(item)
    db.flush()
    return item
