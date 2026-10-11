import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
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
    __table_args__ = (CheckConstraint("status = 'draft'", name="ck_memoirs_status"),)
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
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    memoir_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memoirs.id", ondelete="CASCADE"), index=True
    )
    memory_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memories.id", ondelete="RESTRICT"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
