import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base

V1 = "interview-agent.v1"
V2 = "interview-agent.v2"
V3 = "interview-agent.v3"
PROFILE = "session-text-dialogue.synthetic.v1"

# CHECKs explicitly handle NULL; SQL UNKNOWN must not admit incomplete v2 results.
# JSON shape/ordering and write-once semantics remain Schema/Service-only rules.
STATE_CHECKS = (
    ("ck_agent_contract", f"contract_version IN ('{V1}', '{V2}')"),
    (
        "ck_agent_status",
        (
            f"(contract_version = '{V1}' AND status IN ('idle', 'awaiting_answer', 'ended')) "
            f"OR (contract_version = '{V2}' AND status IN ('idle', 'listening', 'paused', 'ended'))"
        ),
    ),
    ("ck_agent_version", "version >= 0"),
    ("ck_agent_epoch", "generation_epoch >= 0"),
    ("ck_agent_v2_answer", f"contract_version = '{V1}' OR last_consumed_answer_id IS NULL"),
)

_EMPTY_RESULT = (
    "result_kind IS NULL AND result_state_contract_version IS NULL "
    "AND resulting_version IS NULL AND resulting_status IS NULL "
    "AND output_message_id IS NULL AND output_scope_id IS NULL AND question_key IS NULL"
)
_RESULT_SNAPSHOT = (
    "result_kind IS NOT NULL AND result_state_contract_version IS NOT NULL "
    "AND resulting_version IS NOT NULL AND resulting_status IS NOT NULL"
)
TURN_CHECKS = (
    ("ck_agent_turn_contract", f"contract_version IN ('{V1}', '{V2}')"),
    (
        "ck_agent_action",
        (
            f"(contract_version = '{V1}' AND action IN ('start', 'answer', 'skip', 'end')) "
            f"OR (contract_version = '{V2}' "
            "AND action IN ('start', 'request_question', 'pause', 'resume', 'end'))"
        ),
    ),
    ("ck_agent_fingerprint", "length(request_fingerprint) = 32"),
    (
        "ck_agent_execution",
        "execution_status IN ('pending', 'completed', 'failed', 'discarded')",
    ),
    ("ck_agent_reserved_version", "reserved_version IS NULL OR reserved_version >= 0"),
    ("ck_agent_reserved_epoch", "reserved_epoch IS NULL OR reserved_epoch >= 0"),
    ("ck_agent_turn_version", "resulting_version IS NULL OR resulting_version >= 0"),
    (
        "ck_agent_turn_status",
        (
            "(result_state_contract_version IS NULL AND resulting_status IS NULL) "
            f"OR (result_state_contract_version = '{V1}' AND resulting_status IS NOT NULL "
            "AND resulting_status IN ('idle', 'awaiting_answer', 'ended')) "
            f"OR (result_state_contract_version = '{V2}' AND resulting_status IS NOT NULL "
            "AND resulting_status IN ('idle', 'listening', 'paused', 'ended'))"
        ),
    ),
    (
        "ck_agent_turn_version_fields",
        (
            f"(contract_version = '{V1}' AND reserved_version IS NULL AND reserved_epoch IS NULL "
            "AND context_present IS NULL AND context_message_id IS NULL AND context_scope_id IS NULL "
            "AND asked_question_message_ids IS NULL AND provider_id IS NULL) "
            f"OR (contract_version = '{V2}' AND reserved_version IS NOT NULL "
            "AND reserved_epoch IS NOT NULL AND context_present IS NOT NULL "
            "AND asked_question_message_ids IS NOT NULL AND input_answer_id IS NULL "
            "AND question_text_normalized IS NULL)"
        ),
    ),
    (
        "ck_agent_context",
        (
            f"contract_version = '{V1}' OR "
            "(context_present = false AND context_message_id IS NULL AND context_scope_id IS NULL) "
            "OR (context_present = true AND context_scope_id IS NOT NULL "
            "AND (context_message_id IS NULL OR context_message_id = context_scope_id))"
        ),
    ),
    (
        "ck_agent_output_scope",
        (
            "output_message_id IS NULL OR "
            "(output_scope_id IS NOT NULL AND output_message_id = output_scope_id)"
        ),
    ),
    (
        "ck_agent_turn_lifecycle",
        (
            f"(contract_version = '{V1}' AND execution_status = 'completed' "
            f"AND {_RESULT_SNAPSHOT} AND result_state_contract_version = '{V1}' "
            "AND resulting_version > 0 AND resulting_status IN ('awaiting_answer', 'ended') "
            "AND result_kind IN ('control', 'question', 'no_question') "
            "AND failure_code IS NULL AND discard_reason IS NULL) "
            f"OR (contract_version = '{V2}' AND ("
            "(execution_status = 'pending' AND action = 'request_question' AND provider_id IS NOT NULL "
            f"AND {_EMPTY_RESULT} AND failure_code IS NULL AND discard_reason IS NULL "
            "AND finished_at IS NULL) OR "
            "(execution_status = 'failed' AND action = 'request_question' AND provider_id IS NOT NULL "
            f"AND {_EMPTY_RESULT} AND failure_code IS NOT NULL AND discard_reason IS NULL "
            "AND finished_at IS NOT NULL) OR "
            "(execution_status = 'discarded' AND action = 'request_question' "
            f"AND provider_id IS NOT NULL AND {_EMPTY_RESULT} AND failure_code IS NULL "
            "AND discard_reason IS NOT NULL AND finished_at IS NOT NULL) OR "
            f"(execution_status = 'completed' AND {_RESULT_SNAPSHOT} "
            "AND finished_at IS NOT NULL AND failure_code IS NULL AND discard_reason IS NULL "
            "AND ((result_kind = 'control' AND action IN ('start', 'pause', 'resume', 'end') "
            "AND provider_id IS NULL AND context_present = false AND context_message_id IS NULL "
            "AND context_scope_id IS NULL AND output_message_id IS NULL AND output_scope_id IS NULL "
            "AND question_key IS NULL "
            f"AND (result_state_contract_version = '{V2}' "
            f"OR (action = 'end' AND result_state_contract_version = '{V1}' "
            "AND resulting_status = 'ended'))) OR "
            "(result_kind = 'question' AND action = 'request_question' AND provider_id IS NOT NULL "
            "AND question_key IS NOT NULL AND output_scope_id IS NOT NULL "
            f"AND result_state_contract_version = '{V2}' AND resulting_status = 'listening') OR "
            "(result_kind = 'no_question' AND action = 'request_question' AND provider_id IS NOT NULL "
            "AND question_key IS NULL AND output_message_id IS NULL AND output_scope_id IS NULL "
            f"AND result_state_contract_version = '{V2}' AND resulting_status = 'listening')))"
            "))"
        ),
    ),
)


_NEW_STATE = "integration_profile IS NOT NULL AND version >= 0 AND generation_epoch >= 0 AND integration_profile = 'session-text-dialogue.synthetic.v1' AND contract_version = 'interview-agent.v3' AND status IN ('idle','listening','generating','ready','delivering','paused','blocked','ended')"
_NEW_TURN = "integration_profile IS NOT NULL AND integration_profile = 'session-text-dialogue.synthetic.v1' AND contract_version = 'interview-agent.v3' AND execution_status IN ('queued','preparing','completed','failed','discarded')"
STATE_CHECKS = tuple(
    (name, f"(integration_profile IS NULL AND ({sql})) OR ({_NEW_STATE})")
    for name, sql in STATE_CHECKS
)
TURN_CHECKS = tuple(
    (name, f"(integration_profile IS NULL AND ({sql})) OR ({_NEW_TURN})")
    for name, sql in TURN_CHECKS
)


class InterviewAgentState(Base):
    __tablename__ = "interview_agent_states"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in STATE_CHECKS),
        CheckConstraint(
            "(integration_profile IS NULL AND persistence_version IS NULL AND stop_fence IS NULL AND last_applied_event_seq IS NULL AND next_command_order IS NULL AND checkpoint_status IS NULL AND effective_mode IS NULL AND current_context_revision IS NULL AND clock_origin_at IS NULL AND active_command_id IS NULL) OR (integration_profile IS NOT NULL AND persistence_version IS NOT NULL AND persistence_version >= 0 AND stop_fence IS NOT NULL AND stop_fence >= 0 AND last_applied_event_seq IS NOT NULL AND last_applied_event_seq >= 0 AND next_command_order IS NOT NULL AND next_command_order > 0 AND checkpoint_status IS NOT NULL AND checkpoint_status IN ('valid','sync_required','unavailable') AND effective_mode IS NOT NULL AND effective_mode IN ('light','record_only') AND clock_origin_at IS NOT NULL AND (current_context_revision IS NOT NULL OR status IN ('idle','ended')) AND (status != 'ended' OR checkpoint_status = 'unavailable'))",
            name="ck_dialogue_state_profile",
        ),
        ForeignKeyConstraint(
            ["session_id", "current_context_revision"],
            ["interview_agent_contexts.session_id", "interview_agent_contexts.revision"],
            name="fk_dialogue_current_context",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["session_id", "active_command_id"],
            ["interview_agent_turns.session_id", "interview_agent_turns.id"],
            name="fk_dialogue_active_command",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        Index("ix_dialogue_profile_status", "integration_profile", "status"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("interview_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    contract_version: Mapped[str] = mapped_column(String(32), nullable=False, default=V2)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="idle")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generation_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    current_question_message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("interview_messages.id", ondelete="SET NULL")
    )
    last_consumed_answer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("interview_messages.id", ondelete="SET NULL")
    )
    policy_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    integration_profile: Mapped[str | None] = mapped_column(String(64))
    persistence_version: Mapped[int | None] = mapped_column(BigInteger)
    stop_fence: Mapped[int | None] = mapped_column(BigInteger)
    last_applied_event_seq: Mapped[int | None] = mapped_column(BigInteger)
    next_command_order: Mapped[int | None] = mapped_column(BigInteger)
    checkpoint_status: Mapped[str | None] = mapped_column(String(24))
    effective_mode: Mapped[str | None] = mapped_column(String(16))
    current_context_revision: Mapped[int | None] = mapped_column(BigInteger)
    clock_origin_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_command_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class InterviewAgentTurn(Base):
    __tablename__ = "interview_agent_turns"
    __table_args__ = (
        UniqueConstraint("session_id", "idempotency_key", name="uq_agent_turn_key"),
        UniqueConstraint("input_answer_id", name="uq_agent_consumed_answer"),
        UniqueConstraint("session_id", "id", name="uq_dialogue_turn_scope"),
        UniqueConstraint("session_id", "event_id", name="uq_dialogue_event"),
        UniqueConstraint("session_id", "command_order", name="uq_dialogue_order"),
        UniqueConstraint("parent_turn_id", "internal_reason", name="uq_dialogue_child"),
        ForeignKeyConstraint(
            ["session_id", "parent_turn_id"],
            ["interview_agent_turns.session_id", "interview_agent_turns.id"],
            name="fk_dialogue_parent_turn",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "parent_turn_id IS NULL OR parent_turn_id != id", name="ck_dialogue_not_self"
        ),
        CheckConstraint(
            "(integration_profile IS NULL AND command_order IS NULL AND event_id IS NULL AND event_kind IS NULL AND command_payload IS NULL AND fingerprint_key_id IS NULL AND transition_attempts IS NULL AND reserved_event_seq IS NULL AND applied_event_seq IS NULL AND reserved_persistence_version IS NULL AND reserved_stop_fence IS NULL AND result_metadata IS NULL AND parent_turn_id IS NULL AND internal_reason IS NULL AND event_envelope IS NULL) OR (integration_profile IS NOT NULL AND command_order IS NOT NULL AND command_order > 0 AND event_id IS NOT NULL AND event_kind IS NOT NULL AND command_payload IS NOT NULL AND fingerprint_key_id IS NOT NULL AND transition_attempts IS NOT NULL AND length(request_fingerprint) = 32 AND ((parent_turn_id IS NULL AND internal_reason IS NULL) OR (parent_turn_id IS NOT NULL AND internal_reason IS NOT NULL AND internal_reason = 'published_history_refresh' AND event_kind = 'context_refresh')) AND (execution_status != 'preparing' OR (reserved_event_seq IS NOT NULL AND reserved_event_seq > 0 AND reserved_persistence_version IS NOT NULL AND reserved_persistence_version >= 0 AND reserved_stop_fence IS NOT NULL AND reserved_stop_fence >= 0)) AND ((execution_status IN ('queued','preparing') AND finished_at IS NULL AND resulting_version IS NULL) OR (execution_status IN ('completed','failed','discarded') AND finished_at IS NOT NULL)) AND (applied_event_seq IS NULL OR applied_event_seq > 0))",
            name="ck_dialogue_turn_profile",
        ),
        Index(
            "uq_dialogue_preparing",
            "session_id",
            unique=True,
            postgresql_where=text(
                "integration_profile IS NOT NULL AND execution_status = 'preparing'"
            ),
            sqlite_where=text("integration_profile IS NOT NULL AND execution_status = 'preparing'"),
        ),
        Index(
            "uq_dialogue_applied_seq",
            "session_id",
            "applied_event_seq",
            unique=True,
            postgresql_where=text("applied_event_seq IS NOT NULL"),
            sqlite_where=text("applied_event_seq IS NOT NULL"),
        ),
        *(CheckConstraint(sql, name=name) for name, sql in TURN_CHECKS),
        Index(
            "uq_agent_pending_session",
            "session_id",
            unique=True,
            postgresql_where=text("execution_status = 'pending' AND integration_profile IS NULL"),
            sqlite_where=text("execution_status = 'pending' AND integration_profile IS NULL"),
        ),
        Index(
            "uq_agent_v2_output_scope",
            "output_scope_id",
            unique=True,
            postgresql_where=text(f"contract_version = '{V2}' AND output_scope_id IS NOT NULL"),
            sqlite_where=text(f"contract_version = '{V2}' AND output_scope_id IS NOT NULL"),
        ),
        Index("ix_agent_context_message", "context_message_id"),
        Index("ix_agent_session_execution", "session_id", "execution_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    contract_version: Mapped[str] = mapped_column(String(32), nullable=False, default=V2)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    request_fingerprint: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    reserved_version: Mapped[int | None] = mapped_column(Integer)
    reserved_epoch: Mapped[int | None] = mapped_column(BigInteger)
    execution_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    context_present: Mapped[bool | None] = mapped_column(Boolean)
    context_message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("interview_messages.id", ondelete="SET NULL")
    )
    context_scope_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    asked_question_message_ids: Mapped[list[str] | None] = mapped_column(JSON(none_as_null=True))
    provider_id: Mapped[str | None] = mapped_column(String(64))
    input_answer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("interview_messages.id", ondelete="SET NULL")
    )
    output_message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("interview_messages.id", ondelete="SET NULL")
    )
    output_scope_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    question_key: Mapped[str | None] = mapped_column(String(100))
    question_text_normalized: Mapped[str | None] = mapped_column(String(120))
    result_kind: Mapped[str | None] = mapped_column(String(32))
    result_state_contract_version: Mapped[str | None] = mapped_column(String(32))
    resulting_version: Mapped[int | None] = mapped_column(Integer)
    resulting_status: Mapped[str | None] = mapped_column(String(32))
    failure_code: Mapped[str | None] = mapped_column(String(64))
    discard_reason: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    integration_profile: Mapped[str | None] = mapped_column(String(64))
    command_order: Mapped[int | None] = mapped_column(BigInteger)
    event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    event_kind: Mapped[str | None] = mapped_column(String(40))
    command_payload: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    reserved_event_seq: Mapped[int | None] = mapped_column(BigInteger)
    applied_event_seq: Mapped[int | None] = mapped_column(BigInteger)
    reserved_persistence_version: Mapped[int | None] = mapped_column(BigInteger)
    reserved_stop_fence: Mapped[int | None] = mapped_column(BigInteger)
    fingerprint_key_id: Mapped[str | None] = mapped_column(String(100))
    result_metadata: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    parent_turn_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    internal_reason: Mapped[str | None] = mapped_column(String(40))
    event_envelope: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    transition_attempts: Mapped[list | None] = mapped_column(JSON(none_as_null=True))
