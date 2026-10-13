"""Offline Memory Candidate / Revision / review profile. SOURCE ONLY.

Revision: b196f0d47a21
Parent: a196e4c72b08

This migration is self-contained. It does not import application models,
assign historical Speaker/Consent/approval, or execute provider processing.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "b196f0d47a21"
down_revision = "a196e4c72b08"
branch_labels = None
depends_on = None

JSON_VALUE = sa.JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")

MEMORY_COLUMNS = (
    sa.Column("record_origin", sa.String(32), nullable=False, server_default="legacy"),
    sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
    sa.Column("revision_counter", sa.BigInteger(), nullable=False, server_default="0"),
    sa.Column("origin_candidate_id", sa.Uuid(), nullable=True),
    sa.Column("current_revision_id", sa.Uuid(), nullable=True),
    sa.Column("current_approval_proposal_id", sa.Uuid(), nullable=True),
)
MEMORY_CHECKS = (
    ("ck_memories_origin", "record_origin IN ('legacy', 'versioned')"),
    ("ck_memories_counters", "version >= 0 AND revision_counter >= 0"),
    (
        "ck_memories_current_pair",
        (
            "(current_revision_id IS NULL AND current_approval_proposal_id IS NULL) OR "
            "(current_revision_id IS NOT NULL AND current_approval_proposal_id IS NOT NULL)"
        ),
    ),
    (
        "ck_memories_versioned_body",
        (
            "record_origin = 'legacy' OR (title IS NULL AND content IS NULL AND time_text IS NULL "
            "AND place IS NULL AND emotion IS NULL)"
        ),
    ),
)
SECTION_CHECKS = (
    (
        "ck_memoir_sections_origin",
        "record_origin IN ('legacy_snapshot', 'approved_revision_snapshot')",
    ),
    (
        "ck_memoir_sections_proof_pair",
        (
            "(record_origin = 'legacy_snapshot' AND memory_revision_id IS NULL "
            "AND approval_proposal_id IS NULL) OR "
            "(record_origin = 'approved_revision_snapshot' AND memory_revision_id IS NOT NULL "
            "AND approval_proposal_id IS NOT NULL)"
        ),
    ),
)
SECTION_COLUMNS = (
    sa.Column("record_origin", sa.String(32), nullable=False, server_default="legacy_snapshot"),
    sa.Column("memory_revision_id", sa.Uuid(), nullable=True),
    sa.Column("approval_proposal_id", sa.Uuid(), nullable=True),
)
# Deferred until every referenced UNIQUE key exists. Historical FK names are
# intentionally preserved: this migration only introduces the new bindings.
LATE_FOREIGN_KEYS = (
    ("fk_mc_promoted_memory", "memory_candidates", "memories", ["promoted_memory_id"], ["id"]),
    (
        "fk_memories_origin_candidate",
        "memories",
        "memory_candidates",
        ["origin_candidate_id"],
        ["id"],
    ),
    (
        "fk_memories_current_revision",
        "memories",
        "memory_content_revisions",
        ["current_revision_id"],
        ["id"],
    ),
    (
        "fk_memories_current_proposal",
        "memories",
        "revision_proposals",
        ["current_approval_proposal_id"],
        ["id"],
    ),
    (
        "fk_memories_current_proof",
        "memories",
        "revision_proposals",
        ["current_approval_proposal_id", "current_revision_id", "id"],
        ["id", "result_memory_revision_id", "result_memory_id"],
    ),
    (
        "fk_memoir_sections_revision",
        "memoir_sections",
        "memory_content_revisions",
        ["memory_revision_id"],
        ["id"],
    ),
    (
        "fk_memoir_sections_proposal",
        "memoir_sections",
        "revision_proposals",
        ["approval_proposal_id"],
        ["id"],
    ),
    (
        "fk_memoir_sections_proof",
        "memoir_sections",
        "revision_proposals",
        ["approval_proposal_id", "memory_revision_id", "memory_id"],
        ["id", "result_memory_revision_id", "result_memory_id"],
    ),
    (
        "fk_memoir_sections_revision_memory",
        "memoir_sections",
        "memory_content_revisions",
        ["memory_revision_id", "memory_id"],
        ["id", "memory_id"],
    ),
)


def upgrade():
    # The authoritative target is PostgreSQL. The lock prevents concurrent legacy
    # writes during metadata backfill/cutover; SQLite uses the ORM for offline tests.
    op.execute(
        "LOCK TABLE memories, memoirs, memoir_sections, command_idempotency_records "
        "IN ACCESS EXCLUSIVE MODE"
    )
    for column in MEMORY_COLUMNS:
        op.add_column("memories", column)
    op.alter_column("memories", "title", existing_type=sa.String(200), nullable=True)
    op.alter_column("memories", "content", existing_type=sa.Text(), nullable=True)
    op.add_column(
        "memoirs",
        sa.Column("record_origin", sa.String(32), nullable=False, server_default="legacy"),
    )
    for column in SECTION_COLUMNS:
        op.add_column("memoir_sections", column)
    op.add_column("command_idempotency_records", sa.Column("fingerprint_scheme", sa.String(64)))
    op.add_column("command_idempotency_records", sa.Column("fingerprint_key_id", sa.String(100)))

    # Metadata only. IDs, source FKs and legacy source/body bytes are untouched.
    # NULL references deliberately mean no proven historical revision or approval.
    op.execute(
        "UPDATE memories SET record_origin = 'legacy', version = 0, revision_counter = 0, "
        "origin_candidate_id = NULL, current_revision_id = NULL, current_approval_proposal_id = NULL"
    )
    op.execute("UPDATE memoirs SET record_origin = 'legacy'")
    op.execute(
        "UPDATE memoir_sections SET record_origin = 'legacy_snapshot', "
        "memory_revision_id = NULL, approval_proposal_id = NULL"
    )
    op.create_unique_constraint(
        "uq_memories_subject", "memories", ["id", "family_member_id", "source_message_id"]
    )
    op.create_unique_constraint("uq_memories_origin_candidate", "memories", ["origin_candidate_id"])
    _create_workflow_tables()
    for name, table, target, local_columns, target_columns in LATE_FOREIGN_KEYS:
        op.create_foreign_key(
            name, table, target, local_columns, target_columns, ondelete="RESTRICT"
        )
    for name, condition in MEMORY_CHECKS:
        op.create_check_constraint(name, "memories", condition)
    op.create_check_constraint(
        "ck_memoirs_origin", "memoirs", "record_origin IN ('legacy', 'versioned')"
    )
    for name, condition in SECTION_CHECKS:
        op.create_check_constraint(name, "memoir_sections", condition)


def downgrade():
    # Nothing is deleted to make the guard pass. Data rollback is a separate plan.
    # Take the writer lock first so a new B command cannot race the read-only guard.
    op.execute(
        "LOCK TABLE memories, memoirs, memoir_sections, command_idempotency_records, "
        "memory_extraction_batches, memory_candidates, memory_content_revisions, "
        "revision_proposals IN ACCESS EXCLUSIVE MODE"
    )
    has_b_data = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM memory_extraction_batches "
                "UNION ALL SELECT 1 FROM memory_candidates "
                "UNION ALL SELECT 1 FROM memory_content_revisions "
                "UNION ALL SELECT 1 FROM revision_proposals "
                "UNION ALL SELECT 1 FROM memories WHERE record_origin != 'legacy' "
                "OR version != 0 OR revision_counter != 0 OR origin_candidate_id IS NOT NULL "
                "OR current_revision_id IS NOT NULL OR current_approval_proposal_id IS NOT NULL "
                "UNION ALL SELECT 1 FROM memoirs WHERE record_origin != 'legacy' "
                "UNION ALL SELECT 1 FROM memoir_sections WHERE record_origin != 'legacy_snapshot' "
                "OR memory_revision_id IS NOT NULL OR approval_proposal_id IS NOT NULL "
                "UNION ALL SELECT 1 FROM command_idempotency_records "
                "WHERE fingerprint_scheme IS NOT NULL OR fingerprint_key_id IS NOT NULL "
                "OR operation LIKE 'memory.%' OR operation LIKE 'memoir.%' LIMIT 1"
            )
        )
        .first()
    )
    unsafe_legacy = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM memories m LEFT JOIN interview_messages im ON im.id = m.source_message_id "
                "LEFT JOIN family_members fm ON fm.id = m.family_member_id "
                "WHERE m.title IS NULL OR m.content IS NULL OR im.id IS NULL OR fm.id IS NULL LIMIT 1"
            )
        )
        .first()
    )
    if has_b_data is not None or unsafe_legacy is not None:
        raise RuntimeError("Memory workflow downgrade requires a separate data rollback plan")

    for name, table, _target, _local, _remote in reversed(LATE_FOREIGN_KEYS):
        op.drop_constraint(name, table, type_="foreignkey")
    for name, _condition in SECTION_CHECKS:
        op.drop_constraint(name, "memoir_sections", type_="check")
    op.drop_constraint("ck_memoirs_origin", "memoirs", type_="check")
    for name, _condition in MEMORY_CHECKS:
        op.drop_constraint(name, "memories", type_="check")
    for table in (
        "revision_proposals",
        "memory_content_revisions",
        "memory_candidates",
        "memory_extraction_batches",
    ):
        op.drop_table(table)
    op.drop_constraint("uq_memories_subject", "memories", type_="unique")
    op.drop_constraint("uq_memories_origin_candidate", "memories", type_="unique")
    for column in reversed(SECTION_COLUMNS):
        op.drop_column("memoir_sections", column.name)
    op.drop_column("memoirs", "record_origin")
    for column in reversed(MEMORY_COLUMNS):
        op.drop_column("memories", column.name)
    op.drop_column("command_idempotency_records", "fingerprint_key_id")
    op.drop_column("command_idempotency_records", "fingerprint_scheme")
    op.alter_column("memories", "title", existing_type=sa.String(200), nullable=False)
    op.alter_column("memories", "content", existing_type=sa.Text(), nullable=False)


def _create_workflow_tables():
    op.create_table(
        "memory_extraction_batches",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "requested_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT", name="fk_mxb_actor"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("interview_sessions.id", ondelete="RESTRICT", name="fk_mxb_session"),
            nullable=False,
        ),
        sa.Column(
            "family_member_id",
            sa.Uuid(),
            sa.ForeignKey("family_members.id", ondelete="RESTRICT", name="fk_mxb_member"),
            nullable=False,
        ),
        sa.Column("family_scope_id", sa.Uuid(), nullable=False),
        sa.Column(
            "source_message_id",
            sa.Uuid(),
            sa.ForeignKey("interview_messages.id", ondelete="RESTRICT", name="fk_mxb_source"),
            nullable=False,
        ),
        sa.Column("source_scope_id", sa.Uuid(), nullable=False),
        sa.Column("contract_version", sa.String(40), nullable=False),
        sa.Column("policy_version", sa.String(100), nullable=False),
        sa.Column("permission_stamp", JSON_VALUE, nullable=False),
        sa.Column("provider_id", sa.String(64), nullable=False),
        sa.Column("request_fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("candidate_count", sa.Integer(), nullable=True),
        sa.Column("failure_code", sa.String(64), nullable=True),
        sa.Column("discard_reason", sa.String(64), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("requested_by_user_id", "idempotency_key", name="uq_mxb_actor_key"),
        sa.UniqueConstraint("id", "family_member_id", "source_message_id", name="uq_mxb_subject"),
        sa.CheckConstraint("source_scope_id = source_message_id", name="ck_mxb_source_scope"),
        sa.CheckConstraint("version >= 0", name="ck_mxb_version"),
        sa.CheckConstraint("length(request_fingerprint) = 32", name="ck_mxb_fingerprint"),
        sa.CheckConstraint("contract_version = 'memory-extraction.v1'", name="ck_mxb_contract"),
        sa.CheckConstraint("provider_id = 'mock'", name="ck_mxb_provider"),
        sa.CheckConstraint(
            "state IN ('pending', 'completed', 'failed', 'discarded', 'cancelled')",
            name="ck_mxb_state",
        ),
        sa.CheckConstraint(
            "(state = 'pending' AND candidate_count IS NULL AND failure_code IS NULL AND discard_reason IS NULL AND finished_at IS NULL) OR (state = 'completed' AND candidate_count IS NOT NULL AND candidate_count BETWEEN 0 AND 20 AND failure_code IS NULL AND discard_reason IS NULL AND finished_at IS NOT NULL) OR (state = 'failed' AND candidate_count IS NULL AND failure_code IS NOT NULL AND discard_reason IS NULL AND finished_at IS NOT NULL) OR (state = 'discarded' AND candidate_count IS NULL AND failure_code IS NULL AND discard_reason IS NOT NULL AND finished_at IS NOT NULL) OR (state = 'cancelled' AND candidate_count IS NULL AND failure_code IS NULL AND discard_reason IS NOT NULL AND discard_reason = 'cancelled_by_owner' AND finished_at IS NOT NULL)",
            name="ck_mxb_lifecycle",
        ),
    )
    op.create_index(
        "ix_mxb_session_created", "memory_extraction_batches", ["session_id", "created_at", "id"]
    )
    op.create_index(
        "ix_mxb_source_state", "memory_extraction_batches", ["source_message_id", "state"]
    )
    op.create_index(
        "ix_mxb_member_state", "memory_extraction_batches", ["family_member_id", "state"]
    )

    op.create_table(
        "memory_candidates",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "family_member_id",
            sa.Uuid(),
            sa.ForeignKey("family_members.id", ondelete="RESTRICT", name="fk_mc_member"),
            nullable=False,
        ),
        sa.Column("family_scope_id", sa.Uuid(), nullable=False),
        sa.Column(
            "source_message_id",
            sa.Uuid(),
            sa.ForeignKey("interview_messages.id", ondelete="RESTRICT", name="fk_mc_source"),
            nullable=False,
        ),
        sa.Column("source_scope_id", sa.Uuid(), nullable=False),
        sa.Column("origin", sa.String(32), nullable=False),
        sa.Column(
            "batch_id",
            sa.Uuid(),
            sa.ForeignKey("memory_extraction_batches.id", ondelete="RESTRICT", name="fk_mc_batch"),
            nullable=True,
        ),
        sa.Column("batch_ordinal", sa.Integer(), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT", name="fk_mc_actor"),
            nullable=False,
        ),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("revision_counter", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("promoted_memory_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("batch_id", "batch_ordinal", name="uq_mc_batch_ordinal"),
        sa.UniqueConstraint("promoted_memory_id", name="uq_mc_promoted_memory"),
        sa.UniqueConstraint("id", "family_member_id", "source_message_id", name="uq_mc_subject"),
        sa.ForeignKeyConstraint(
            ["batch_id", "family_member_id", "source_message_id"],
            [
                "memory_extraction_batches.id",
                "memory_extraction_batches.family_member_id",
                "memory_extraction_batches.source_message_id",
            ],
            ondelete="RESTRICT",
            name="fk_mc_batch_subject",
        ),
        sa.CheckConstraint("source_scope_id = source_message_id", name="ck_mc_source_scope"),
        sa.CheckConstraint("version >= 0 AND revision_counter >= 0", name="ck_mc_counters"),
        sa.CheckConstraint("origin IN ('extraction', 'manual')", name="ck_mc_origin"),
        sa.CheckConstraint(
            "(origin = 'manual' AND batch_id IS NULL AND batch_ordinal IS NULL) OR (origin = 'extraction' AND batch_id IS NOT NULL AND batch_ordinal IS NOT NULL AND batch_ordinal >= 1)",
            name="ck_mc_batch_origin",
        ),
        sa.CheckConstraint(
            "(promoted_memory_id IS NULL AND version = 0) OR (promoted_memory_id IS NOT NULL AND version = 1)",
            name="ck_mc_promotion",
        ),
    )
    op.create_index(
        "ix_mc_member_created", "memory_candidates", ["family_member_id", "created_at", "id"]
    )
    op.create_index("ix_mc_source", "memory_candidates", ["source_message_id"])
    op.create_index("ix_mc_batch", "memory_candidates", ["batch_id"])

    op.create_table(
        "memory_content_revisions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "candidate_id",
            sa.Uuid(),
            sa.ForeignKey("memory_candidates.id", ondelete="RESTRICT", name="fk_mcr_candidate"),
            nullable=True,
        ),
        sa.Column(
            "memory_id",
            sa.Uuid(),
            sa.ForeignKey("memories.id", ondelete="RESTRICT", name="fk_mcr_memory"),
            nullable=True,
        ),
        sa.Column(
            "family_member_id",
            sa.Uuid(),
            sa.ForeignKey("family_members.id", ondelete="RESTRICT", name="fk_mcr_member"),
            nullable=False,
        ),
        sa.Column("family_scope_id", sa.Uuid(), nullable=False),
        sa.Column(
            "source_message_id",
            sa.Uuid(),
            sa.ForeignKey("interview_messages.id", ondelete="RESTRICT", name="fk_mcr_source"),
            nullable=False,
        ),
        sa.Column("source_scope_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.BigInteger(), nullable=False),
        sa.Column(
            "parent_revision_id",
            sa.Uuid(),
            sa.ForeignKey("memory_content_revisions.id", ondelete="RESTRICT", name="fk_mcr_parent"),
            nullable=True,
        ),
        sa.Column(
            "origin_revision_id",
            sa.Uuid(),
            sa.ForeignKey("memory_content_revisions.id", ondelete="RESTRICT", name="fk_mcr_origin"),
            nullable=True,
        ),
        sa.Column("author_mode", sa.String(32), nullable=False),
        sa.Column(
            "actor_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT", name="fk_mcr_actor"),
            nullable=False,
        ),
        sa.Column("derivation_profile", sa.String(64), nullable=False),
        sa.Column("required_purposes", JSON_VALUE, nullable=False),
        sa.Column("input_permission_stamp", JSON_VALUE, nullable=False),
        sa.Column("body_state", sa.String(16), nullable=False),
        sa.Column("payload", JSON_VALUE, nullable=True),
        sa.Column("content_digest", sa.LargeBinary(), nullable=True),
        sa.Column("digest_scheme", sa.String(64), nullable=True),
        sa.Column("digest_key_id", sa.String(100), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("candidate_id", "ordinal", name="uq_mcr_candidate_ordinal"),
        sa.UniqueConstraint("memory_id", "ordinal", name="uq_mcr_memory_ordinal"),
        sa.UniqueConstraint("id", "candidate_id", name="uq_mcr_candidate"),
        sa.UniqueConstraint("id", "memory_id", name="uq_mcr_memory"),
        sa.UniqueConstraint(
            "id", "candidate_id", "family_member_id", name="uq_mcr_candidate_member"
        ),
        sa.UniqueConstraint("id", "memory_id", "family_member_id", name="uq_mcr_memory_member"),
        sa.ForeignKeyConstraint(
            ["candidate_id", "family_member_id", "source_message_id"],
            [
                "memory_candidates.id",
                "memory_candidates.family_member_id",
                "memory_candidates.source_message_id",
            ],
            name="fk_mcr_candidate_subject",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["memory_id", "family_member_id", "source_message_id"],
            ["memories.id", "memories.family_member_id", "memories.source_message_id"],
            name="fk_mcr_memory_subject",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parent_revision_id", "candidate_id"],
            ["memory_content_revisions.id", "memory_content_revisions.candidate_id"],
            name="fk_mcr_parent_candidate",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parent_revision_id", "memory_id"],
            ["memory_content_revisions.id", "memory_content_revisions.memory_id"],
            name="fk_mcr_parent_memory",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "(candidate_id IS NULL AND memory_id IS NOT NULL) OR (candidate_id IS NOT NULL AND memory_id IS NULL)",
            name="ck_mcr_target",
        ),
        sa.CheckConstraint("source_scope_id = source_message_id", name="ck_mcr_source_scope"),
        sa.CheckConstraint("ordinal >= 1", name="ck_mcr_ordinal"),
        sa.CheckConstraint(
            "author_mode IN ('mock_ai', 'manual', 'promotion')", name="ck_mcr_author"
        ),
        sa.CheckConstraint(
            "derivation_profile IN ('raw_manual', 'ai_derived', 'transcript_derived', 'inherited')",
            name="ck_mcr_derivation",
        ),
        sa.CheckConstraint("body_state IN ('present', 'purged')", name="ck_mcr_body_state"),
        sa.CheckConstraint(
            "(body_state = 'present' AND payload IS NOT NULL AND content_digest IS NOT NULL AND digest_scheme IS NOT NULL AND digest_key_id IS NOT NULL AND length(content_digest) = 32) OR (body_state = 'purged' AND payload IS NULL AND content_digest IS NULL AND digest_scheme IS NULL AND digest_key_id IS NULL)",
            name="ck_mcr_body",
        ),
    )
    op.create_index("ix_mcr_source", "memory_content_revisions", ["source_message_id"])
    op.create_index("ix_mcr_parent", "memory_content_revisions", ["parent_revision_id"])
    op.create_index("ix_mcr_origin", "memory_content_revisions", ["origin_revision_id"])

    op.create_table(
        "revision_proposals",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("profile", sa.String(40), nullable=False),
        sa.Column("family_scope_id", sa.Uuid(), nullable=False),
        sa.Column(
            "family_member_id",
            sa.Uuid(),
            sa.ForeignKey("family_members.id", ondelete="RESTRICT", name="fk_rp_member"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            sa.Uuid(),
            sa.ForeignKey("memory_candidates.id", ondelete="RESTRICT", name="fk_rp_candidate"),
            nullable=True,
        ),
        sa.Column(
            "memory_id",
            sa.Uuid(),
            sa.ForeignKey("memories.id", ondelete="RESTRICT", name="fk_rp_memory"),
            nullable=True,
        ),
        sa.Column(
            "input_revision_id",
            sa.Uuid(),
            sa.ForeignKey("memory_content_revisions.id", ondelete="RESTRICT", name="fk_rp_input"),
            nullable=False,
        ),
        sa.Column(
            "proposed_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT", name="fk_rp_actor"),
            nullable=False,
        ),
        sa.Column("base_version", sa.BigInteger(), nullable=False),
        sa.Column(
            "base_revision_id",
            sa.Uuid(),
            sa.ForeignKey("memory_content_revisions.id", ondelete="RESTRICT", name="fk_rp_base"),
            nullable=True,
        ),
        sa.Column("payload_digest", sa.LargeBinary(), nullable=True),
        sa.Column("digest_scheme", sa.String(64), nullable=True),
        sa.Column("digest_key_id", sa.String(100), nullable=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "decided_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT", name="fk_rp_decider"),
            nullable=True,
        ),
        sa.Column("decision_code", sa.String(64), nullable=True),
        sa.Column("approval_permission_stamp", JSON_VALUE, nullable=True),
        sa.Column(
            "result_memory_id",
            sa.Uuid(),
            sa.ForeignKey("memories.id", ondelete="RESTRICT", name="fk_rp_result_target"),
            nullable=True,
        ),
        sa.Column(
            "result_memory_revision_id",
            sa.Uuid(),
            sa.ForeignKey(
                "memory_content_revisions.id", ondelete="RESTRICT", name="fk_rp_result_revision"
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("input_revision_id", name="uq_rp_input"),
        sa.UniqueConstraint(
            "id", "result_memory_revision_id", "result_memory_id", name="uq_rp_result"
        ),
        sa.ForeignKeyConstraint(
            ["input_revision_id", "candidate_id"],
            ["memory_content_revisions.id", "memory_content_revisions.candidate_id"],
            name="fk_rp_input_candidate",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["input_revision_id", "memory_id"],
            ["memory_content_revisions.id", "memory_content_revisions.memory_id"],
            name="fk_rp_input_memory",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["input_revision_id", "candidate_id", "family_member_id"],
            [
                "memory_content_revisions.id",
                "memory_content_revisions.candidate_id",
                "memory_content_revisions.family_member_id",
            ],
            name="fk_rp_input_candidate_member",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["input_revision_id", "memory_id", "family_member_id"],
            [
                "memory_content_revisions.id",
                "memory_content_revisions.memory_id",
                "memory_content_revisions.family_member_id",
            ],
            name="fk_rp_input_memory_member",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["base_revision_id", "memory_id"],
            ["memory_content_revisions.id", "memory_content_revisions.memory_id"],
            name="fk_rp_base_memory",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["result_memory_revision_id", "result_memory_id"],
            ["memory_content_revisions.id", "memory_content_revisions.memory_id"],
            name="fk_rp_result_memory",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("profile = 'offline_memory.v1'", name="ck_rp_profile"),
        sa.CheckConstraint(
            "(candidate_id IS NULL AND memory_id IS NOT NULL) OR (candidate_id IS NOT NULL AND memory_id IS NULL)",
            name="ck_rp_target",
        ),
        sa.CheckConstraint("candidate_id IS NULL OR base_revision_id IS NULL", name="ck_rp_base"),
        sa.CheckConstraint("base_version >= 0 AND version >= 0", name="ck_rp_versions"),
        sa.CheckConstraint(
            "state IN ('draft', 'submitted', 'approved', 'rejected', 'withdrawn', 'stale', 'purged')",
            name="ck_rp_state",
        ),
        sa.CheckConstraint(
            "(result_memory_id IS NULL AND result_memory_revision_id IS NULL) OR (result_memory_id IS NOT NULL AND result_memory_revision_id IS NOT NULL)",
            name="ck_rp_result_pair",
        ),
        sa.CheckConstraint(
            "(state != 'purged' AND payload_digest IS NOT NULL AND length(payload_digest) = 32 AND digest_scheme IS NOT NULL AND digest_key_id IS NOT NULL) OR (state = 'purged' AND ((payload_digest IS NULL AND digest_scheme IS NULL AND digest_key_id IS NULL) OR (payload_digest IS NOT NULL AND length(payload_digest) = 32 AND digest_scheme IS NOT NULL AND digest_key_id IS NOT NULL)))",
            name="ck_rp_digest",
        ),
        sa.CheckConstraint(
            "(state = 'draft' AND submitted_at IS NULL AND decided_at IS NULL AND decided_by_user_id IS NULL AND result_memory_id IS NULL AND approval_permission_stamp IS NULL) OR (state = 'submitted' AND submitted_at IS NOT NULL AND decided_at IS NULL AND decided_by_user_id IS NULL AND result_memory_id IS NULL AND approval_permission_stamp IS NULL) OR (state = 'approved' AND submitted_at IS NOT NULL AND decided_at IS NOT NULL AND decided_by_user_id IS NOT NULL AND result_memory_id IS NOT NULL AND approval_permission_stamp IS NOT NULL) OR (state = 'rejected' AND submitted_at IS NOT NULL AND decided_at IS NOT NULL AND decided_by_user_id IS NOT NULL AND result_memory_id IS NULL AND approval_permission_stamp IS NULL) OR (state = 'withdrawn' AND decided_at IS NOT NULL AND decided_by_user_id IS NOT NULL AND result_memory_id IS NULL AND approval_permission_stamp IS NULL) OR (state = 'stale' AND submitted_at IS NOT NULL AND decided_at IS NOT NULL AND decided_by_user_id IS NULL AND result_memory_id IS NULL AND approval_permission_stamp IS NULL) OR state = 'purged'",
            name="ck_rp_lifecycle",
        ),
        sa.CheckConstraint(
            "state != 'approved' OR memory_id IS NULL OR (result_memory_id = memory_id AND result_memory_revision_id = input_revision_id)",
            name="ck_rp_memory_result",
        ),
    )
    op.create_index(
        "ix_rp_scope_state_created",
        "revision_proposals",
        ["family_scope_id", "state", "created_at", "id"],
    )
    op.create_index("ix_rp_memory_state", "revision_proposals", ["memory_id", "state"])
    op.create_index("ix_rp_candidate_state", "revision_proposals", ["candidate_id", "state"])
