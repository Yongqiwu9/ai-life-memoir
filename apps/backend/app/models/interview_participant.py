import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    event,
    func,
    inspect,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class InterviewParticipant(Base):
    __tablename__ = "interview_participants"
    __table_args__ = (
        ForeignKeyConstraint(
            ["verified_contact_id", "user_id"],
            ["user_contacts.id", "user_contacts.user_id"],
            name="fk_interview_participants_verified_contact_user",
            ondelete="RESTRICT",
        ),
        CheckConstraint("roles = 'speaker'", name="ck_interview_participants_roles"),
        CheckConstraint(
            "state IN ('proposed', 'verified', 'inactive', 'disputed')",
            name="ck_interview_participants_state",
        ),
        CheckConstraint(
            "eligibility_state IN ('unknown', 'eligible', 'ineligible')",
            name="ck_interview_participants_eligibility",
        ),
        CheckConstraint(
            "(state = 'proposed' AND eligibility_state = 'unknown') OR "
            "(state = 'verified' AND eligibility_state = 'eligible') OR "
            "(state = 'inactive' AND eligibility_state IN ('eligible', 'ineligible')) OR "
            "(state = 'disputed')",
            name="ck_interview_participants_state_eligibility",
        ),
        CheckConstraint(
            "state != 'verified' OR (user_id IS NOT NULL AND verified_contact_id IS NOT NULL "
            "AND verification_ref IS NOT NULL AND verified_at IS NOT NULL "
            "AND adult_declaration_at IS NOT NULL AND eligibility_state = 'eligible')",
            name="ck_interview_participants_verified_evidence",
        ),
        CheckConstraint(
            "state != 'proposed' OR (user_id IS NULL AND verified_contact_id IS NULL "
            "AND verification_ref IS NULL AND verified_at IS NULL "
            "AND adult_declaration_at IS NULL)",
            name="ck_interview_participants_proposed_unclaimed",
        ),
        CheckConstraint("version > 0", name="ck_interview_participants_version"),
        UniqueConstraint(
            "id",
            "interview_scope_id",
            name="uq_interview_participants_id_scope",
        ),
        Index(
            "uq_interview_participants_scope_user",
            "interview_scope_id",
            "user_id",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
            sqlite_where=text("user_id IS NOT NULL"),
        ),
        Index("ix_interview_participants_interview_state", "interview_id", "state"),
        Index("ix_interview_participants_scope_state", "interview_scope_id", "state"),
        Index("ix_interview_participants_user_state", "user_id", "state"),
        Index("ix_interview_participants_family_member", "family_member_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    interview_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("interviews.id", ondelete="SET NULL"), nullable=True
    )
    interview_scope_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    family_member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("family_members.id", ondelete="SET NULL"), nullable=True
    )
    roles: Mapped[str] = mapped_column(String(32), default="speaker", nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="proposed", nullable=False)
    eligibility_state: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    verified_contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    verification_ref: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    adult_declaration_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(BigInteger, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


@event.listens_for(InterviewParticipant, "before_update")
def _protect_participant_identity(_mapper, _connection, target):
    state = inspect(target)
    immutable = ("interview_scope_id", "roles", "family_member_id")
    if any(state.attrs[name].history.has_changes() for name in immutable):
        raise ValueError("Participant scope is immutable")
    user_history = state.attrs.user_id.history
    if user_history.has_changes() and any(value is not None for value in user_history.deleted):
        raise ValueError("Participant user claim is immutable")
    for name in ("verified_contact_id", "verification_ref", "verified_at", "adult_declaration_at"):
        history = state.attrs[name].history
        if history.has_changes() and any(value is not None for value in history.deleted):
            raise ValueError("Participant verification evidence is immutable")
