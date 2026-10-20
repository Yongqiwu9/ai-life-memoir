"""Subordinate storage for the explicitly allocated synthetic dialogue profile."""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base

DOCUMENT = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AgentContext(Timestamps, Base):
    __tablename__ = "interview_agent_contexts"
    __table_args__ = (
        UniqueConstraint("context_id", name="uq_dialogue_context_id"),
        UniqueConstraint("session_id", "context_id", name="uq_dialogue_context_scope"),
        CheckConstraint(
            "revision > 0 AND manifest_version > 0 AND purpose = 'dialogue'",
            name="ck_dialogue_context",
        ),
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("interview_agent_states.session_id", ondelete="CASCADE"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    context_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    manifest_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    manifest_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)
    context_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    source_order: Mapped[list] = mapped_column(DOCUMENT, nullable=False)
    history_order: Mapped[list] = mapped_column(DOCUMENT, nullable=False)
    quote_slices: Mapped[list] = mapped_column(DOCUMENT, nullable=False)
    asked_keys: Mapped[list] = mapped_column(DOCUMENT, nullable=False)
    skipped_keys: Mapped[list] = mapped_column(DOCUMENT, nullable=False)


class AgentCheckpoint(Timestamps, Base):
    __tablename__ = "interview_agent_checkpoints"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "context_revision"],
            ["interview_agent_contexts.session_id", "interview_agent_contexts.revision"],
            name="fk_dialogue_checkpoint_context",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "checkpoint_version >= 0 AND core_version >= 0 AND core_epoch >= 0 AND last_seq >= 0 AND context_revision > 0",
            name="ck_dialogue_checkpoint_versions",
        ),
        CheckConstraint(
            "content_status IN ('live','quarantined','purged') AND (content_status = 'live' OR sensitive_json IS NULL)",
            name="ck_dialogue_checkpoint_content",
        ),
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("interview_agent_states.session_id", ondelete="CASCADE"), primary_key=True
    )
    checkpoint_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    core_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    core_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    context_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    format_version: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(DOCUMENT, nullable=False)
    sensitive_json: Mapped[dict | None] = mapped_column(DOCUMENT, deferred=True)
    metadata_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    checkpoint_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    integrity_key_id: Mapped[str] = mapped_column(String(100), nullable=False)
    content_status: Mapped[str] = mapped_column(String(16), nullable=False)


class AgentSource(Timestamps, Base):
    __tablename__ = "interview_agent_sources"
    __table_args__ = (
        UniqueConstraint("session_id", "message_sequence", name="uq_dialogue_source_sequence"),
        CheckConstraint(
            "live_message_id IS NULL OR live_message_id = stable_message_id",
            name="ck_dialogue_source_identity",
        ),
        CheckConstraint(
            "version_ordinal = 1 AND message_sequence > 0 AND origin = 'user_text' AND source_role = 'user' AND availability IN ('available','restricted','missing')",
            name="ck_dialogue_source_profile",
        ),
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("interview_agent_states.session_id", ondelete="CASCADE"), primary_key=True
    )
    stable_message_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    live_message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("interview_messages.id", ondelete="SET NULL")
    )
    message_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    source_role: Mapped[str] = mapped_column(String(16), nullable=False)
    version_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    availability: Mapped[str] = mapped_column(String(16), nullable=False)


class AgentEffect(Timestamps, Base):
    __tablename__ = "interview_agent_effects"
    __table_args__ = (
        UniqueConstraint("session_id", "id", name="uq_dialogue_effect_scope"),
        ForeignKeyConstraint(
            ["session_id", "origin_turn_id"],
            ["interview_agent_turns.session_id", "interview_agent_turns.id"],
            name="fk_dialogue_effect_turn",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["session_id", "context_revision"],
            ["interview_agent_contexts.session_id", "interview_agent_contexts.revision"],
            name="fk_dialogue_effect_context",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "kind IN ('generate','deliver','cancel_generation','stop_playback') AND status IN ('reserved','claimed','ready','published','completed','failed','discarded','unknown') AND epoch >= 0 AND stop_fence >= 0",
            name="ck_dialogue_effect_status",
        ),
        CheckConstraint(
            "output_message_id IS NULL OR (output_stable_id IS NOT NULL AND output_message_id = output_stable_id)",
            name="ck_dialogue_output_identity",
        ),
        CheckConstraint(
            "token_digest IS NULL OR length(token_digest) = 32", name="ck_dialogue_token"
        ),
        CheckConstraint(
            "status NOT IN ('completed','failed','discarded','unknown') OR finished_at IS NOT NULL",
            name="ck_dialogue_effect_finished",
        ),
        CheckConstraint(
            "dispatch_outcome IN ('not_sent','sent','returned','unknown')",
            name="ck_dialogue_dispatch",
        ),
        Index(
            "uq_dialogue_generate_response",
            "response_id",
            unique=True,
            postgresql_where=text("kind='generate' AND response_id IS NOT NULL"),
            sqlite_where=text("kind='generate' AND response_id IS NOT NULL"),
        ),
        Index(
            "uq_dialogue_output",
            "output_stable_id",
            unique=True,
            postgresql_where=text("output_stable_id IS NOT NULL"),
            sqlite_where=text("output_stable_id IS NOT NULL"),
        ),
        Index(
            "uq_dialogue_busy_generate",
            "session_id",
            unique=True,
            postgresql_where=text("kind='generate' AND status IN ('reserved','claimed','ready')"),
            sqlite_where=text("kind='generate' AND status IN ('reserved','claimed','ready')"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("interview_agent_states.session_id", ondelete="CASCADE"), nullable=False
    )
    origin_turn_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    epoch: Mapped[int] = mapped_column(BigInteger, nullable=False)
    stop_fence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    context_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    binding_json: Mapped[dict] = mapped_column(DOCUMENT, nullable=False)
    response_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    output_message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("interview_messages.id", ondelete="SET NULL")
    )
    output_stable_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    token_digest: Mapped[bytes | None] = mapped_column(LargeBinary)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatch_outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observation_code: Mapped[str | None] = mapped_column(String(64))


class AgentDependency(Timestamps, Base):
    __tablename__ = "interview_agent_dependencies"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "source_message_id"],
            ["interview_agent_sources.session_id", "interview_agent_sources.stable_message_id"],
            name="fk_dialogue_dependency_source",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["session_id", "context_revision"],
            ["interview_agent_contexts.session_id", "interview_agent_contexts.revision"],
            name="fk_dialogue_dependency_context",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["session_id", "effect_id"],
            ["interview_agent_effects.session_id", "interview_agent_effects.id"],
            name="fk_dialogue_dependency_effect",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "(owner_kind='context' AND context_revision IS NOT NULL AND effect_id IS NULL AND checkpoint_session_id IS NULL) OR (owner_kind='effect' AND context_revision IS NULL AND effect_id IS NOT NULL AND checkpoint_session_id IS NULL) OR (owner_kind='checkpoint' AND context_revision IS NULL AND effect_id IS NULL AND checkpoint_session_id IS NOT NULL AND checkpoint_session_id=session_id)",
            name="ck_dialogue_dependency_owner",
        ),
        Index("ix_dialogue_source_dependents", "session_id", "source_message_id", "owner_kind"),
        Index(
            "uq_dialogue_context_dependency",
            "session_id",
            "context_revision",
            "source_message_id",
            unique=True,
            postgresql_where=text("owner_kind='context'"),
            sqlite_where=text("owner_kind='context'"),
        ),
        Index(
            "uq_dialogue_effect_dependency",
            "session_id",
            "effect_id",
            "source_message_id",
            unique=True,
            postgresql_where=text("owner_kind='effect'"),
            sqlite_where=text("owner_kind='effect'"),
        ),
        Index(
            "uq_dialogue_checkpoint_dependency",
            "session_id",
            "source_message_id",
            unique=True,
            postgresql_where=text("owner_kind='checkpoint'"),
            sqlite_where=text("owner_kind='checkpoint'"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("interview_agent_states.session_id", ondelete="CASCADE"), nullable=False
    )
    source_message_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    owner_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    context_revision: Mapped[int | None] = mapped_column(BigInteger)
    effect_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    checkpoint_session_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("interview_agent_checkpoints.session_id", ondelete="CASCADE")
    )
