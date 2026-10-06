import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    Uuid,
    event,
    func,
    inspect,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class CollaborationTimestamps:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CommandIdempotencyRecord(Base):
    __tablename__ = "command_idempotency_records"
    __table_args__ = (
        CheckConstraint(
            "state IN ('processing', 'completed', 'failed_retryable')",
            name="ck_command_idempotency_state",
        ),
        CheckConstraint("length(request_digest) = 32", name="ck_command_idempotency_digest"),
        CheckConstraint(
            "response_status IS NULL OR (response_status >= 100 AND response_status <= 599)",
            name="ck_command_idempotency_response_status",
        ),
        Index(
            "uq_command_idempotency_actor",
            "actor_user_id",
            "operation",
            "idempotency_key",
            unique=True,
            postgresql_where=text("actor_user_id IS NOT NULL"),
            sqlite_where=text("actor_user_id IS NOT NULL"),
        ),
        Index(
            "uq_command_idempotency_anonymous",
            "operation",
            "idempotency_key",
            unique=True,
            postgresql_where=text("actor_user_id IS NULL"),
            sqlite_where=text("actor_user_id IS NULL"),
        ),
        Index("ix_command_idempotency_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    request_digest: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="processing", nullable=False)
    resource_kind: Mapped[str | None] = mapped_column(String(64))
    resource_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FamilyInvitation(CollaborationTimestamps, Base):
    __tablename__ = "family_invitations"
    __table_args__ = (
        CheckConstraint(
            "state IN ('pending_owner', 'approved', 'accepted', 'rejected', "
            "'cancelled', 'revoked', 'expired')",
            name="ck_family_invitations_state",
        ),
        CheckConstraint("version > 0", name="ck_family_invitations_version"),
        CheckConstraint(
            "length(recipient_hash) = 32 AND length(recipient_ciphertext) > 0",
            name="ck_family_invitations_recipient_storage",
        ),
        CheckConstraint(
            "token_digest IS NULL OR length(token_digest) = 32",
            name="ck_family_invitations_token_digest",
        ),
        CheckConstraint(
            "state != 'pending_owner' OR (approved_by_user_id IS NULL AND approved_at IS NULL "
            "AND token_digest IS NULL AND accepted_at IS NULL)",
            name="ck_family_invitations_pending",
        ),
        CheckConstraint(
            "state NOT IN ('approved', 'accepted', 'revoked', 'expired') OR "
            "(approved_by_user_id IS NOT NULL AND approved_at IS NOT NULL "
            "AND expires_at IS NOT NULL AND token_digest IS NOT NULL)",
            name="ck_family_invitations_approval",
        ),
        CheckConstraint(
            "state != 'accepted' OR (accepted_at IS NOT NULL AND recipient_user_id IS NOT NULL)",
            name="ck_family_invitations_acceptance",
        ),
        Index(
            "uq_family_invitations_active_recipient",
            "family_id",
            "recipient_hash",
            unique=True,
            postgresql_where=text("state IN ('pending_owner', 'approved')"),
            sqlite_where=text("state IN ('pending_owner', 'approved')"),
        ),
        Index(
            "uq_family_invitations_token_digest",
            "token_digest",
            unique=True,
            postgresql_where=text("token_digest IS NOT NULL"),
            sqlite_where=text("token_digest IS NOT NULL"),
        ),
        Index("ix_family_invitations_family_state", "family_id", "state"),
        Index("ix_family_invitations_recipient_user", "recipient_user_id", "state"),
        Index("ix_family_invitations_requested_by", "requested_by_user_id"),
        Index("ix_family_invitations_approved_by", "approved_by_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), nullable=False
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    recipient_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    recipient_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    recipient_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    token_digest: Mapped[bytes | None] = mapped_column(LargeBinary)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(BigInteger, default=1, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FamilyMembership(CollaborationTimestamps, Base):
    __tablename__ = "family_memberships"
    __table_args__ = (
        UniqueConstraint("family_id", "user_id", name="uq_family_memberships_family_user"),
        CheckConstraint("role = 'collaborator'", name="ck_family_memberships_role"),
        CheckConstraint(
            "state IN ('active', 'revoked', 'left')", name="ck_family_memberships_state"
        ),
        CheckConstraint("generation > 0", name="ck_family_memberships_generation"),
        CheckConstraint(
            "(state = 'active' AND ended_at IS NULL) OR "
            "(state IN ('revoked', 'left') AND ended_at IS NOT NULL)",
            name="ck_family_memberships_end_state",
        ),
        Index("ix_family_memberships_user_state", "user_id", "state"),
        Index("ix_family_memberships_family_state", "family_id", "state"),
        Index("ix_family_memberships_accepted_invitation", "accepted_invitation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), default="collaborator", nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    generation: Mapped[int] = mapped_column(BigInteger, default=1, nullable=False)
    accepted_invitation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("family_invitations.id", ondelete="SET NULL")
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


@event.listens_for(FamilyInvitation, "before_update")
def _protect_invitation_identity(_mapper, _connection, target):
    state = inspect(target)
    immutable = ("family_id", "requested_by_user_id", "recipient_hash", "recipient_ciphertext")
    if any(state.attrs[name].history.has_changes() for name in immutable):
        raise ValueError("Invitation identity is immutable")
    recipient_history = state.attrs.recipient_user_id.history
    if recipient_history.has_changes() and any(
        previous is not None for previous in recipient_history.deleted
    ):
        raise ValueError("Resolved invitation recipient is immutable")


@event.listens_for(FamilyMembership, "before_update")
def _protect_membership_identity(_mapper, _connection, target):
    state = inspect(target)
    immutable = ("family_id", "user_id", "role")
    if any(state.attrs[name].history.has_changes() for name in immutable):
        raise ValueError("Membership identity is immutable")


@event.listens_for(CommandIdempotencyRecord, "before_update")
def _protect_idempotency_identity(_mapper, _connection, target):
    state = inspect(target)
    immutable = ("actor_user_id", "operation", "idempotency_key", "request_digest")
    if any(state.attrs[name].history.has_changes() for name in immutable):
        raise ValueError("Idempotency command identity is immutable")
    old_states = state.attrs.state.history.deleted
    if old_states and old_states[0] == "completed":
        raise ValueError("Completed idempotency record is immutable")
