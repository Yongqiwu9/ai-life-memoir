import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
    func,
    inspect,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Memoir(Base):
    __tablename__ = "memoirs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    family_member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("family_members.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="draft", server_default="draft")
    record_origin: Mapped[str] = mapped_column(
        String(32), default="legacy", server_default="legacy"
    )
    __table_args__ = (
        CheckConstraint("status = 'draft'", name="ck_memoirs_status"),
        CheckConstraint("record_origin IN ('legacy', 'versioned')", name="ck_memoirs_origin"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sections: Mapped[list["MemoirSection"]] = relationship(
        cascade="all, delete-orphan", order_by="MemoirSection.position"
    )


class MemoirSection(Base):
    __tablename__ = "memoir_sections"
    __table_args__ = (
        UniqueConstraint("memoir_id", "position", name="uq_memoir_sections_position"),
        UniqueConstraint("memoir_id", "memory_id", name="uq_memoir_sections_memory"),
        CheckConstraint("position > 0", name="ck_memoir_sections_position"),
        ForeignKeyConstraint(
            ["approval_proposal_id", "memory_revision_id", "memory_id"],
            [
                "revision_proposals.id",
                "revision_proposals.result_memory_revision_id",
                "revision_proposals.result_memory_id",
            ],
            name="fk_memoir_sections_proof",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["memory_revision_id", "memory_id"],
            ["memory_content_revisions.id", "memory_content_revisions.memory_id"],
            name="fk_memoir_sections_revision_memory",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "record_origin IN ('legacy_snapshot', 'approved_revision_snapshot')",
            name="ck_memoir_sections_origin",
        ),
        CheckConstraint(
            "(record_origin = 'legacy_snapshot' AND memory_revision_id IS NULL "
            "AND approval_proposal_id IS NULL) OR "
            "(record_origin = 'approved_revision_snapshot' AND memory_revision_id IS NOT NULL "
            "AND approval_proposal_id IS NOT NULL)",
            name="ck_memoir_sections_proof_pair",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    memoir_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memoirs.id", ondelete="CASCADE"), index=True
    )
    memory_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memories.id", ondelete="RESTRICT"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    record_origin: Mapped[str] = mapped_column(
        String(32), default="legacy_snapshot", server_default="legacy_snapshot"
    )
    memory_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "memory_content_revisions.id", ondelete="RESTRICT", name="fk_memoir_sections_revision"
        )
    )
    approval_proposal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("revision_proposals.id", ondelete="RESTRICT", name="fk_memoir_sections_proposal")
    )
    title: Mapped[str] = mapped_column(String(200), deferred=True)
    content: Mapped[str] = mapped_column(Text, deferred=True)


@event.listens_for(MemoirSection, "before_update")
def _protect_section_snapshot(_mapper, _connection, target):
    state = inspect(target)
    immutable = (
        "id",
        "memoir_id",
        "memory_id",
        "position",
        "record_origin",
        "memory_revision_id",
        "approval_proposal_id",
        "title",
        "content",
    )
    if any(state.attrs[name].history.has_changes() for name in immutable):
        raise ValueError("Memoir section snapshot and proof are immutable")
