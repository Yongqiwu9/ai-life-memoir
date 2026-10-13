"""Offline Memory review profile. No real Consent or Artifact authority is implied."""

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
    event,
    func,
    inspect,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base

JSON_VALUE = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")

# Exact table/constraint pairs only. Other internal FK violations are not classified
# as protected legacy parent deletion, and neither 23502 nor 23505 is accepted.
PROTECTED_DELETE_FK_MANIFEST = frozenset(
    {
        ("memory_extraction_batches", "fk_mxb_session"),
        ("memory_extraction_batches", "fk_mxb_source"),
        ("memory_extraction_batches", "fk_mxb_member"),
        ("memory_candidates", "fk_mc_source"),
        ("memory_candidates", "fk_mc_member"),
        ("memory_content_revisions", "fk_mcr_source"),
        ("memory_content_revisions", "fk_mcr_member"),
        ("revision_proposals", "fk_rp_member"),
        ("memories", "memories_source_message_id_fkey"),
        ("memories", "memories_family_member_id_fkey"),
        ("memoirs", "memoirs_family_member_id_fkey"),
    }
)
PROTECTED_PARENT_FKS = PROTECTED_DELETE_FK_MANIFEST


class WorkflowTimestamps:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ExtractionBatch(WorkflowTimestamps, Base):
    __tablename__ = "memory_extraction_batches"
    __table_args__ = (
        UniqueConstraint("requested_by_user_id", "idempotency_key", name="uq_mxb_actor_key"),
        UniqueConstraint("id", "family_member_id", "source_message_id", name="uq_mxb_subject"),
        CheckConstraint("source_scope_id = source_message_id", name="ck_mxb_source_scope"),
        CheckConstraint("version >= 0", name="ck_mxb_version"),
        CheckConstraint("length(request_fingerprint) = 32", name="ck_mxb_fingerprint"),
        CheckConstraint("contract_version = 'memory-extraction.v1'", name="ck_mxb_contract"),
        CheckConstraint("provider_id = 'mock'", name="ck_mxb_provider"),
        CheckConstraint(
            "state IN ('pending', 'completed', 'failed', 'discarded', 'cancelled')",
            name="ck_mxb_state",
        ),
        CheckConstraint(
            "(state = 'pending' AND candidate_count IS NULL AND failure_code IS NULL "
            "AND discard_reason IS NULL AND finished_at IS NULL) OR "
            "(state = 'completed' AND candidate_count IS NOT NULL "
            "AND candidate_count BETWEEN 0 AND 20 AND failure_code IS NULL "
            "AND discard_reason IS NULL AND finished_at IS NOT NULL) OR "
            "(state = 'failed' AND candidate_count IS NULL AND failure_code IS NOT NULL "
            "AND discard_reason IS NULL AND finished_at IS NOT NULL) OR "
            "(state = 'discarded' AND candidate_count IS NULL AND failure_code IS NULL "
            "AND discard_reason IS NOT NULL AND finished_at IS NOT NULL) OR "
            "(state = 'cancelled' AND candidate_count IS NULL AND failure_code IS NULL "
            "AND discard_reason IS NOT NULL AND discard_reason = 'cancelled_by_owner' "
            "AND finished_at IS NOT NULL)",
            name="ck_mxb_lifecycle",
        ),
        Index("ix_mxb_session_created", "session_id", "created_at", "id"),
        Index("ix_mxb_source_state", "source_message_id", "state"),
        Index("ix_mxb_member_state", "family_member_id", "state"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_mxb_actor")
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="RESTRICT", name="fk_mxb_session")
    )
    family_member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("family_members.id", ondelete="RESTRICT", name="fk_mxb_member")
    )
    family_scope_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    source_message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interview_messages.id", ondelete="RESTRICT", name="fk_mxb_source")
    )
    source_scope_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    contract_version: Mapped[str] = mapped_column(String(40), default="memory-extraction.v1")
    policy_version: Mapped[str] = mapped_column(String(100))
    permission_stamp: Mapped[dict] = mapped_column(JSON_VALUE, deferred=True)
    provider_id: Mapped[str] = mapped_column(String(64), default="mock")
    request_fingerprint: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    idempotency_key: Mapped[uuid.UUID] = mapped_column(Uuid)
    state: Mapped[str] = mapped_column(String(32), default="pending", active_history=True)
    version: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    candidate_count: Mapped[int | None] = mapped_column(Integer)
    failure_code: Mapped[str | None] = mapped_column(String(64))
    discard_reason: Mapped[str | None] = mapped_column(String(64))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MemoryCandidate(WorkflowTimestamps, Base):
    __tablename__ = "memory_candidates"
    __table_args__ = (
        UniqueConstraint("batch_id", "batch_ordinal", name="uq_mc_batch_ordinal"),
        UniqueConstraint("promoted_memory_id", name="uq_mc_promoted_memory"),
        UniqueConstraint("id", "family_member_id", "source_message_id", name="uq_mc_subject"),
        ForeignKeyConstraint(
            ["batch_id", "family_member_id", "source_message_id"],
            [
                "memory_extraction_batches.id",
                "memory_extraction_batches.family_member_id",
                "memory_extraction_batches.source_message_id",
            ],
            ondelete="RESTRICT",
            name="fk_mc_batch_subject",
        ),
        CheckConstraint("source_scope_id = source_message_id", name="ck_mc_source_scope"),
        CheckConstraint("version >= 0 AND revision_counter >= 0", name="ck_mc_counters"),
        CheckConstraint("origin IN ('extraction', 'manual')", name="ck_mc_origin"),
        CheckConstraint(
            "(origin = 'manual' AND batch_id IS NULL AND batch_ordinal IS NULL) OR "
            "(origin = 'extraction' AND batch_id IS NOT NULL AND batch_ordinal IS NOT NULL "
            "AND batch_ordinal >= 1)",
            name="ck_mc_batch_origin",
        ),
        CheckConstraint(
            "(promoted_memory_id IS NULL AND version = 0) OR "
            "(promoted_memory_id IS NOT NULL AND version = 1)",
            name="ck_mc_promotion",
        ),
        Index("ix_mc_member_created", "family_member_id", "created_at", "id"),
        Index("ix_mc_source", "source_message_id"),
        Index("ix_mc_batch", "batch_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    family_member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("family_members.id", ondelete="RESTRICT", name="fk_mc_member")
    )
    family_scope_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    source_message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interview_messages.id", ondelete="RESTRICT", name="fk_mc_source")
    )
    source_scope_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    origin: Mapped[str] = mapped_column(String(32))
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memory_extraction_batches.id", ondelete="RESTRICT", name="fk_mc_batch")
    )
    batch_ordinal: Mapped[int | None] = mapped_column(Integer)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_mc_actor")
    )
    version: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    revision_counter: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    promoted_memory_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "memories.id", ondelete="RESTRICT", name="fk_mc_promoted_memory", use_alter=True
        ),
        active_history=True,
    )


class ContentRevision(WorkflowTimestamps, Base):
    __tablename__ = "memory_content_revisions"
    __table_args__ = (
        UniqueConstraint("candidate_id", "ordinal", name="uq_mcr_candidate_ordinal"),
        UniqueConstraint("memory_id", "ordinal", name="uq_mcr_memory_ordinal"),
        UniqueConstraint("id", "candidate_id", name="uq_mcr_candidate"),
        UniqueConstraint("id", "memory_id", name="uq_mcr_memory"),
        UniqueConstraint("id", "candidate_id", "family_member_id", name="uq_mcr_candidate_member"),
        UniqueConstraint("id", "memory_id", "family_member_id", name="uq_mcr_memory_member"),
        ForeignKeyConstraint(
            ["candidate_id", "family_member_id", "source_message_id"],
            [
                "memory_candidates.id",
                "memory_candidates.family_member_id",
                "memory_candidates.source_message_id",
            ],
            name="fk_mcr_candidate_subject",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["memory_id", "family_member_id", "source_message_id"],
            ["memories.id", "memories.family_member_id", "memories.source_message_id"],
            name="fk_mcr_memory_subject",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["parent_revision_id", "candidate_id"],
            ["memory_content_revisions.id", "memory_content_revisions.candidate_id"],
            name="fk_mcr_parent_candidate",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["parent_revision_id", "memory_id"],
            ["memory_content_revisions.id", "memory_content_revisions.memory_id"],
            name="fk_mcr_parent_memory",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(candidate_id IS NULL AND memory_id IS NOT NULL) OR "
            "(candidate_id IS NOT NULL AND memory_id IS NULL)",
            name="ck_mcr_target",
        ),
        CheckConstraint("source_scope_id = source_message_id", name="ck_mcr_source_scope"),
        CheckConstraint("ordinal >= 1", name="ck_mcr_ordinal"),
        CheckConstraint("author_mode IN ('mock_ai', 'manual', 'promotion')", name="ck_mcr_author"),
        CheckConstraint(
            "derivation_profile IN ('raw_manual', 'ai_derived', 'transcript_derived', 'inherited')",
            name="ck_mcr_derivation",
        ),
        CheckConstraint("body_state IN ('present', 'purged')", name="ck_mcr_body_state"),
        CheckConstraint(
            "(body_state = 'present' AND payload IS NOT NULL AND content_digest IS NOT NULL "
            "AND digest_scheme IS NOT NULL AND digest_key_id IS NOT NULL "
            "AND length(content_digest) = 32) OR "
            "(body_state = 'purged' AND payload IS NULL AND content_digest IS NULL "
            "AND digest_scheme IS NULL AND digest_key_id IS NULL)",
            name="ck_mcr_body",
        ),
        Index("ix_mcr_source", "source_message_id"),
        Index("ix_mcr_parent", "parent_revision_id"),
        Index("ix_mcr_origin", "origin_revision_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memory_candidates.id", ondelete="RESTRICT", name="fk_mcr_candidate")
    )
    memory_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memories.id", ondelete="RESTRICT", name="fk_mcr_memory")
    )
    family_member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("family_members.id", ondelete="RESTRICT", name="fk_mcr_member")
    )
    family_scope_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    source_message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interview_messages.id", ondelete="RESTRICT", name="fk_mcr_source")
    )
    source_scope_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    ordinal: Mapped[int] = mapped_column(BigInteger)
    parent_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memory_content_revisions.id", ondelete="RESTRICT", name="fk_mcr_parent")
    )
    origin_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memory_content_revisions.id", ondelete="RESTRICT", name="fk_mcr_origin")
    )
    author_mode: Mapped[str] = mapped_column(String(32))
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_mcr_actor")
    )
    derivation_profile: Mapped[str] = mapped_column(String(64))
    required_purposes: Mapped[list[str]] = mapped_column(JSON_VALUE)
    input_permission_stamp: Mapped[dict] = mapped_column(JSON_VALUE, deferred=True)
    body_state: Mapped[str] = mapped_column(String(16), default="present")
    payload: Mapped[dict | None] = mapped_column(JSON_VALUE, deferred=True)
    content_digest: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    digest_scheme: Mapped[str | None] = mapped_column(String(64))
    digest_key_id: Mapped[str | None] = mapped_column(String(100))


class RevisionProposal(WorkflowTimestamps, Base):
    __tablename__ = "revision_proposals"
    __table_args__ = (
        UniqueConstraint("input_revision_id", name="uq_rp_input"),
        UniqueConstraint(
            "id", "result_memory_revision_id", "result_memory_id", name="uq_rp_result"
        ),
        ForeignKeyConstraint(
            ["input_revision_id", "candidate_id"],
            ["memory_content_revisions.id", "memory_content_revisions.candidate_id"],
            name="fk_rp_input_candidate",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["input_revision_id", "memory_id"],
            ["memory_content_revisions.id", "memory_content_revisions.memory_id"],
            name="fk_rp_input_memory",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["input_revision_id", "candidate_id", "family_member_id"],
            [
                "memory_content_revisions.id",
                "memory_content_revisions.candidate_id",
                "memory_content_revisions.family_member_id",
            ],
            name="fk_rp_input_candidate_member",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["input_revision_id", "memory_id", "family_member_id"],
            [
                "memory_content_revisions.id",
                "memory_content_revisions.memory_id",
                "memory_content_revisions.family_member_id",
            ],
            name="fk_rp_input_memory_member",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["base_revision_id", "memory_id"],
            ["memory_content_revisions.id", "memory_content_revisions.memory_id"],
            name="fk_rp_base_memory",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["result_memory_revision_id", "result_memory_id"],
            ["memory_content_revisions.id", "memory_content_revisions.memory_id"],
            name="fk_rp_result_memory",
            ondelete="RESTRICT",
        ),
        CheckConstraint("profile = 'offline_memory.v1'", name="ck_rp_profile"),
        CheckConstraint(
            "(candidate_id IS NULL AND memory_id IS NOT NULL) OR "
            "(candidate_id IS NOT NULL AND memory_id IS NULL)",
            name="ck_rp_target",
        ),
        CheckConstraint("candidate_id IS NULL OR base_revision_id IS NULL", name="ck_rp_base"),
        CheckConstraint("base_version >= 0 AND version >= 0", name="ck_rp_versions"),
        CheckConstraint(
            "state IN ('draft', 'submitted', 'approved', 'rejected', 'withdrawn', 'stale', 'purged')",
            name="ck_rp_state",
        ),
        CheckConstraint(
            "(result_memory_id IS NULL AND result_memory_revision_id IS NULL) OR "
            "(result_memory_id IS NOT NULL AND result_memory_revision_id IS NOT NULL)",
            name="ck_rp_result_pair",
        ),
        CheckConstraint(
            "(state != 'purged' AND payload_digest IS NOT NULL AND length(payload_digest) = 32 "
            "AND digest_scheme IS NOT NULL AND digest_key_id IS NOT NULL) OR "
            "(state = 'purged' AND ((payload_digest IS NULL AND digest_scheme IS NULL "
            "AND digest_key_id IS NULL) OR (payload_digest IS NOT NULL "
            "AND length(payload_digest) = 32 AND digest_scheme IS NOT NULL "
            "AND digest_key_id IS NOT NULL)))",
            name="ck_rp_digest",
        ),
        CheckConstraint(
            "(state = 'draft' AND submitted_at IS NULL AND decided_at IS NULL "
            "AND decided_by_user_id IS NULL AND result_memory_id IS NULL "
            "AND approval_permission_stamp IS NULL) OR "
            "(state = 'submitted' AND submitted_at IS NOT NULL AND decided_at IS NULL "
            "AND decided_by_user_id IS NULL AND result_memory_id IS NULL "
            "AND approval_permission_stamp IS NULL) OR "
            "(state = 'approved' AND submitted_at IS NOT NULL AND decided_at IS NOT NULL "
            "AND decided_by_user_id IS NOT NULL AND result_memory_id IS NOT NULL "
            "AND approval_permission_stamp IS NOT NULL) OR "
            "(state = 'rejected' AND submitted_at IS NOT NULL AND decided_at IS NOT NULL "
            "AND decided_by_user_id IS NOT NULL AND result_memory_id IS NULL "
            "AND approval_permission_stamp IS NULL) OR "
            "(state = 'withdrawn' AND decided_at IS NOT NULL AND decided_by_user_id IS NOT NULL "
            "AND result_memory_id IS NULL AND approval_permission_stamp IS NULL) OR "
            "(state = 'stale' AND submitted_at IS NOT NULL AND decided_at IS NOT NULL "
            "AND decided_by_user_id IS NULL AND result_memory_id IS NULL "
            "AND approval_permission_stamp IS NULL) OR state = 'purged'",
            name="ck_rp_lifecycle",
        ),
        CheckConstraint(
            "state != 'approved' OR memory_id IS NULL OR "
            "(result_memory_id = memory_id AND result_memory_revision_id = input_revision_id)",
            name="ck_rp_memory_result",
        ),
        Index("ix_rp_scope_state_created", "family_scope_id", "state", "created_at", "id"),
        Index("ix_rp_memory_state", "memory_id", "state"),
        Index("ix_rp_candidate_state", "candidate_id", "state"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    profile: Mapped[str] = mapped_column(String(40), default="offline_memory.v1")
    family_scope_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    family_member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("family_members.id", ondelete="RESTRICT", name="fk_rp_member")
    )
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memory_candidates.id", ondelete="RESTRICT", name="fk_rp_candidate")
    )
    memory_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memories.id", ondelete="RESTRICT", name="fk_rp_memory")
    )
    input_revision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memory_content_revisions.id", ondelete="RESTRICT", name="fk_rp_input")
    )
    proposed_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_rp_actor")
    )
    base_version: Mapped[int] = mapped_column(BigInteger)
    base_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memory_content_revisions.id", ondelete="RESTRICT", name="fk_rp_base")
    )
    payload_digest: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    digest_scheme: Mapped[str | None] = mapped_column(String(64))
    digest_key_id: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(32), default="draft", active_history=True)
    version: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_rp_decider")
    )
    decision_code: Mapped[str | None] = mapped_column(String(64))
    approval_permission_stamp: Mapped[dict | None] = mapped_column(
        JSON_VALUE, deferred=True, active_history=True
    )
    result_memory_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memories.id", ondelete="RESTRICT", name="fk_rp_result_target"),
        active_history=True,
    )
    result_memory_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "memory_content_revisions.id", ondelete="RESTRICT", name="fk_rp_result_revision"
        ),
        active_history=True,
    )


def _protect_fields(target, names, label):
    state = inspect(target)
    if any(state.attrs[name].history.has_changes() for name in names):
        raise ValueError(f"{label} is immutable")


@event.listens_for(ExtractionBatch, "before_update")
def _protect_batch(_mapper, _connection, target):
    _protect_fields(
        target,
        (
            "id",
            "requested_by_user_id",
            "session_id",
            "family_member_id",
            "family_scope_id",
            "source_message_id",
            "source_scope_id",
            "contract_version",
            "policy_version",
            "permission_stamp",
            "provider_id",
            "request_fingerprint",
            "idempotency_key",
            "created_at",
        ),
        "Extraction request",
    )
    old_states = inspect(target).attrs.state.history.deleted
    old_state = old_states[0] if old_states else target.state
    if old_state != "pending":
        raise ValueError("Extraction terminal state is immutable")


@event.listens_for(MemoryCandidate, "before_update")
def _protect_candidate(_mapper, _connection, target):
    _protect_fields(
        target,
        (
            "id",
            "family_member_id",
            "family_scope_id",
            "source_message_id",
            "source_scope_id",
            "origin",
            "batch_id",
            "batch_ordinal",
            "created_by_user_id",
            "created_at",
        ),
        "Candidate source",
    )
    previous = inspect(target).attrs.promoted_memory_id.history.deleted
    if previous and previous[0] is not None:
        raise ValueError("Candidate promotion is immutable")


@event.listens_for(ContentRevision, "before_update")
def _protect_revision(_mapper, _connection, target):
    _protect_fields(
        target,
        (
            "id",
            "candidate_id",
            "memory_id",
            "family_member_id",
            "family_scope_id",
            "source_message_id",
            "source_scope_id",
            "ordinal",
            "parent_revision_id",
            "origin_revision_id",
            "author_mode",
            "actor_user_id",
            "derivation_profile",
            "required_purposes",
            "input_permission_stamp",
            "created_at",
        ),
        "Revision identity and dependencies",
    )
    state = inspect(target)
    private = ("payload", "content_digest", "digest_scheme", "digest_key_id")
    is_purge = target.body_state == "purged" and all(
        getattr(target, field) is None for field in private
    )
    if not is_purge:
        _protect_fields(target, (*private, "body_state"), "Revision body")
    if state.attrs.body_state.history.deleted == ["purged"]:
        raise ValueError("Purged revision cannot be restored")


@event.listens_for(RevisionProposal, "before_update")
def _protect_proposal(_mapper, _connection, target):
    _protect_fields(
        target,
        (
            "id",
            "profile",
            "family_scope_id",
            "family_member_id",
            "candidate_id",
            "memory_id",
            "input_revision_id",
            "proposed_by_user_id",
            "base_version",
            "base_revision_id",
            "created_at",
        ),
        "Proposal input",
    )
    state = inspect(target)
    # Purging may erase all digest fields or retain the existing proof. It must
    # not install a different proof under the privacy-cleanup exception.
    digest_fields = ("payload_digest", "digest_scheme", "digest_key_id")
    clearing_digest = target.state == "purged" and all(
        getattr(target, field) is None for field in digest_fields
    )
    if not clearing_digest:
        _protect_fields(target, digest_fields, "Proposal digest")
    old_states = state.attrs.state.history.deleted
    old_state = old_states[0] if old_states else target.state
    if old_state in {"approved", "rejected", "withdrawn", "stale", "purged"} and (
        target.state != "purged" or old_state == "purged"
    ):
        raise ValueError("Proposal terminal state cannot be reopened")
    for field in ("result_memory_id", "result_memory_revision_id", "approval_permission_stamp"):
        previous = state.attrs[field].history.deleted
        if previous and previous[0] is not None:
            raise ValueError("Proposal result is immutable")
