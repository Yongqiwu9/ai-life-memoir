"""Dormant C3.1 ORM prototype; not registered in production metadata discovery.

Content integration, migration/backfill and PostgreSQL write guards belong to
later C3 phases. Structural checks do not authorize content use or transitions.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class SourceArtifact(Base):
    __tablename__ = "source_artifacts"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('audio_recording', 'transcript', 'transcript_segment', 'interview_message')",
            name="ck_source_artifacts_kind",
        ),
        CheckConstraint(
            "entity_id IS NOT NULL AND interview_scope_id IS NOT NULL",
            name="ck_source_artifacts_c3_identity",
        ),
        CheckConstraint(
            "state IN ('legacy_unknown', 'available', 'quarantined', 'deletion_pending', 'erased')",
            name="ck_source_artifacts_state",
        ),
        CheckConstraint("generation > 0", name="ck_source_artifacts_generation"),
        CheckConstraint("locator IS NULL", name="ck_source_artifacts_locator_null"),
        UniqueConstraint("kind", "entity_id", name="uq_source_artifacts_kind_entity"),
        UniqueConstraint("id", "family_scope_id", name="uq_source_artifacts_id_family_scope"),
        UniqueConstraint("id", "interview_scope_id", name="uq_source_artifacts_id_interview_scope"),
        Index("ix_source_artifacts_family_state", "family_scope_id", "state"),
        Index("ix_source_artifacts_interview_state", "interview_scope_id", "state"),
        Index("ix_source_artifacts_family_generation", "family_scope_id", "generation"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("families.id", ondelete="SET NULL"), nullable=True, index=True
    )
    interview_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("interviews.id", ondelete="SET NULL"), nullable=True, index=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    family_scope_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    interview_scope_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    operator_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_digest: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    locator: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql"),
        nullable=True,
    )
    policy_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("privacy_policy_versions.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
