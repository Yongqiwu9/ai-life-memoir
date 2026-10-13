import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
    func,
    inspect,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Memory(Base):
    __tablename__ = "memories"
    __table_args__ = (
        UniqueConstraint("id", "family_member_id", "source_message_id", name="uq_memories_subject"),
        UniqueConstraint("origin_candidate_id", name="uq_memories_origin_candidate"),
        ForeignKeyConstraint(
            ["current_approval_proposal_id", "current_revision_id", "id"],
            [
                "revision_proposals.id",
                "revision_proposals.result_memory_revision_id",
                "revision_proposals.result_memory_id",
            ],
            name="fk_memories_current_proof",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        CheckConstraint("record_origin IN ('legacy', 'versioned')", name="ck_memories_origin"),
        CheckConstraint("version >= 0 AND revision_counter >= 0", name="ck_memories_counters"),
        CheckConstraint(
            "(current_revision_id IS NULL AND current_approval_proposal_id IS NULL) OR "
            "(current_revision_id IS NOT NULL AND current_approval_proposal_id IS NOT NULL)",
            name="ck_memories_current_pair",
        ),
        CheckConstraint(
            "record_origin = 'legacy' OR (title IS NULL AND content IS NULL AND time_text IS NULL "
            "AND place IS NULL AND emotion IS NULL)",
            name="ck_memories_versioned_body",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    family_member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("family_members.id", ondelete="RESTRICT"), index=True
    )
    source_message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interview_messages.id", ondelete="RESTRICT"), index=True
    )
    record_origin: Mapped[str] = mapped_column(
        String(32), default="legacy", server_default="legacy"
    )
    version: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    revision_counter: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    origin_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "memory_candidates.id",
            ondelete="RESTRICT",
            name="fk_memories_origin_candidate",
            use_alter=True,
        )
    )
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "memory_content_revisions.id",
            ondelete="RESTRICT",
            name="fk_memories_current_revision",
            use_alter=True,
        )
    )
    current_approval_proposal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "revision_proposals.id",
            ondelete="RESTRICT",
            name="fk_memories_current_proposal",
            use_alter=True,
        )
    )
    title: Mapped[str | None] = mapped_column(String(200), deferred=True)
    content: Mapped[str | None] = mapped_column(Text, deferred=True)
    time_text: Mapped[str | None] = mapped_column(String(200), deferred=True)
    place: Mapped[str | None] = mapped_column(String(200), deferred=True)
    emotion: Mapped[str | None] = mapped_column(String(100), deferred=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


@event.listens_for(Memory, "before_update")
def _protect_memory_history(_mapper, _connection, target):
    state = inspect(target)
    immutable = (
        "id",
        "family_member_id",
        "source_message_id",
        "record_origin",
        "origin_candidate_id",
        "title",
        "content",
        "time_text",
        "place",
        "emotion",
        "created_at",
    )
    if any(state.attrs[name].history.has_changes() for name in immutable):
        raise ValueError("Memory source and Legacy snapshot are immutable")
