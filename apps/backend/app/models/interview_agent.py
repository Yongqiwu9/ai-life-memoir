import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
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


class InterviewAgentState(Base):
    __tablename__ = "interview_agent_states"
    __table_args__ = tuple(CheckConstraint(sql, name=name) for name, sql in STATE_CHECKS)

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    contract_version: Mapped[str] = mapped_column(String(32), nullable=False, default=V2)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="idle")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generation_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    current_question_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("interview_messages.id", ondelete="SET NULL")
    )
    last_consumed_answer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("interview_messages.id", ondelete="SET NULL")
    )
    policy_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InterviewAgentTurn(Base):
    __tablename__ = "interview_agent_turns"
    __table_args__ = (
        UniqueConstraint("session_id", "idempotency_key", name="uq_agent_turn_key"),
        UniqueConstraint("input_answer_id", name="uq_agent_consumed_answer"),
        *(CheckConstraint(sql, name=name) for name, sql in TURN_CHECKS),
        Index(
            "uq_agent_pending_session",
            "session_id",
            unique=True,
            postgresql_where=text("execution_status = 'pending'"),
            sqlite_where=text("execution_status = 'pending'"),
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
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
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
        ForeignKey("interview_messages.id", ondelete="SET NULL")
    )
    context_scope_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    asked_question_message_ids: Mapped[list[str] | None] = mapped_column(JSON(none_as_null=True))
    provider_id: Mapped[str | None] = mapped_column(String(64))
    input_answer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("interview_messages.id", ondelete="SET NULL")
    )
    output_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("interview_messages.id", ondelete="SET NULL")
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
