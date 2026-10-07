"""C1 only: policy, contact and challenge storage; no Speaker/Consent entities."""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
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


class IdentityTimestamps:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PrivacyPolicyVersion(IdentityTimestamps, Base):
    __tablename__ = "privacy_policy_versions"
    __table_args__ = (
        CheckConstraint("state IN ('draft', 'active', 'retired')", name="ck_privacy_policy_state"),
        CheckConstraint("length(digest) = 32", name="ck_privacy_policy_digest"),
        CheckConstraint(
            "(state = 'draft' AND published_at IS NULL) OR (state IN ('active', 'retired') AND published_at IS NOT NULL)",
            name="ck_privacy_policy_published",
        ),
        Index(
            "uq_privacy_policy_active",
            "state",
            unique=True,
            postgresql_where=text("state = 'active'"),
            sqlite_where=text("state = 'active'"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    version: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    parameters: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False
    )
    notices: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False
    )
    capabilities: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False
    )
    digest: Mapped[bytes] = mapped_column(LargeBinary, unique=True, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserContact(IdentityTimestamps, Base):
    __tablename__ = "user_contacts"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_user_contacts_id_user"),
        CheckConstraint("kind IN ('email', 'phone')", name="ck_user_contact_kind"),
        CheckConstraint(
            "state IN ('pending', 'verified', 'revoked', 'legacy_unverified')",
            name="ck_user_contact_state",
        ),
        CheckConstraint(
            "length(value_ciphertext) > 0 AND length(lookup_hash) = 32",
            name="ck_user_contact_storage",
        ),
        CheckConstraint(
            "state != 'verified' OR verified_at IS NOT NULL", name="ck_user_contact_verified"
        ),
        CheckConstraint(
            "state != 'revoked' OR revoked_at IS NOT NULL", name="ck_user_contact_revoked"
        ),
        Index(
            "uq_user_contact_effective_channel",
            "kind",
            "lookup_hash",
            unique=True,
            postgresql_where=text("state IN ('pending', 'verified')"),
            sqlite_where=text("state IN ('pending', 'verified')"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    value_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    lookup_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class AuthChallenge(IdentityTimestamps, Base):
    __tablename__ = "auth_challenges"
    __table_args__ = (
        CheckConstraint(
            "state IN ('pending', 'verified', 'consumed', 'expired', 'locked')",
            name="ck_auth_challenge_state",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_auth_challenge_attempt_count"),
        CheckConstraint(
            "length(code_digest) = 32 AND length(channel_hash) = 32 AND length(channel_ciphertext) > 0",
            name="ck_auth_challenge_storage",
        ),
        CheckConstraint(
            "state != 'consumed' OR (consumed_at IS NOT NULL AND user_id IS NOT NULL)",
            name="ck_auth_challenge_consumed",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    context_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    context_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    channel_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    channel_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    code_digest: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


@event.listens_for(PrivacyPolicyVersion, "before_update")
def _protect_published_policy(_mapper, _connection, target):
    state = inspect(target)
    history = state.attrs.published_at.history
    published_before = bool(history.deleted and history.deleted[0] is not None) or (
        target.published_at is not None and not history.added
    )
    if published_before:
        fields = ("version", "parameters", "notices", "capabilities", "digest", "published_at")
        if any(state.attrs[name].history.has_changes() for name in fields):
            raise ValueError("Published policy is immutable")
        if state.attrs.state.history.has_changes() and target.state != "retired":
            raise ValueError("Published policy cannot be reactivated")


@event.listens_for(AuthChallenge, "before_update")
def _protect_challenge_context(_mapper, _connection, target):
    fields = (
        "context_kind",
        "context_id",
        "channel_ciphertext",
        "channel_hash",
        "code_digest",
        "expires_at",
    )
    if any(inspect(target).attrs[name].history.has_changes() for name in fields):
        raise ValueError("Challenge context is immutable")


@event.listens_for(PrivacyPolicyVersion, "before_delete")
def _protect_policy_delete(_mapper, _connection, target):
    if target.published_at is not None:
        raise ValueError("Published policy is immutable")
