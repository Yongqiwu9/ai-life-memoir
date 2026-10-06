"""Part 9.5.5-C2A family collaboration foundation.

Revision ID: b7e2c4d891a0
Revises: c1a7d45e92b0
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b7e2c4d891a0"
down_revision = "c1a7d45e92b0"
branch_labels = None
depends_on = None


def _timestamps():
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade():
    op.create_table(
        "command_idempotency_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("operation", sa.String(100), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("request_digest", sa.LargeBinary(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("resource_kind", sa.String(64)),
        sa.Column("resource_id", sa.Uuid()),
        sa.Column("response_status", sa.Integer()),
        sa.Column("response_body", postgresql.JSONB()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "state IN ('processing', 'completed', 'failed_retryable')",
            name="ck_command_idempotency_state",
        ),
        sa.CheckConstraint("length(request_digest) = 32", name="ck_command_idempotency_digest"),
        sa.CheckConstraint(
            "response_status IS NULL OR (response_status >= 100 AND response_status <= 599)",
            name="ck_command_idempotency_response_status",
        ),
    )
    op.create_index(
        "uq_command_idempotency_actor",
        "command_idempotency_records",
        ["actor_user_id", "operation", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("actor_user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_command_idempotency_anonymous",
        "command_idempotency_records",
        ["operation", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("actor_user_id IS NULL"),
    )
    op.create_index(
        "ix_command_idempotency_expires_at",
        "command_idempotency_records",
        ["expires_at"],
    )

    op.create_table(
        "family_invitations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "family_id",
            sa.Uuid(),
            sa.ForeignKey("families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "requested_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("recipient_hash", sa.LargeBinary(), nullable=False),
        sa.Column("recipient_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("recipient_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("approved_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("token_digest", sa.LargeBinary()),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.CheckConstraint(
            "state IN ('pending_owner', 'approved', 'accepted', 'rejected', "
            "'cancelled', 'revoked', 'expired')",
            name="ck_family_invitations_state",
        ),
        sa.CheckConstraint("version > 0", name="ck_family_invitations_version"),
        sa.CheckConstraint(
            "length(recipient_hash) = 32 AND length(recipient_ciphertext) > 0",
            name="ck_family_invitations_recipient_storage",
        ),
        sa.CheckConstraint(
            "token_digest IS NULL OR length(token_digest) = 32",
            name="ck_family_invitations_token_digest",
        ),
        sa.CheckConstraint(
            "state != 'pending_owner' OR (approved_by_user_id IS NULL AND approved_at IS NULL "
            "AND token_digest IS NULL AND accepted_at IS NULL)",
            name="ck_family_invitations_pending",
        ),
        sa.CheckConstraint(
            "state NOT IN ('approved', 'accepted', 'revoked', 'expired') OR "
            "(approved_by_user_id IS NOT NULL AND approved_at IS NOT NULL "
            "AND expires_at IS NOT NULL AND token_digest IS NOT NULL)",
            name="ck_family_invitations_approval",
        ),
        sa.CheckConstraint(
            "state != 'accepted' OR (accepted_at IS NOT NULL AND recipient_user_id IS NOT NULL)",
            name="ck_family_invitations_acceptance",
        ),
    )
    op.create_index(
        "uq_family_invitations_active_recipient",
        "family_invitations",
        ["family_id", "recipient_hash"],
        unique=True,
        postgresql_where=sa.text("state IN ('pending_owner', 'approved')"),
    )
    op.create_index(
        "uq_family_invitations_token_digest",
        "family_invitations",
        ["token_digest"],
        unique=True,
        postgresql_where=sa.text("token_digest IS NOT NULL"),
    )
    for name, columns in (
        ("ix_family_invitations_family_state", ["family_id", "state"]),
        ("ix_family_invitations_recipient_user", ["recipient_user_id", "state"]),
        ("ix_family_invitations_requested_by", ["requested_by_user_id"]),
        ("ix_family_invitations_approved_by", ["approved_by_user_id"]),
    ):
        op.create_index(name, "family_invitations", columns)

    op.create_table(
        "family_memberships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "family_id",
            sa.Uuid(),
            sa.ForeignKey("families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column(
            "accepted_invitation_id",
            sa.Uuid(),
            sa.ForeignKey("family_invitations.id", ondelete="SET NULL"),
        ),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.UniqueConstraint("family_id", "user_id", name="uq_family_memberships_family_user"),
        sa.CheckConstraint("role = 'collaborator'", name="ck_family_memberships_role"),
        sa.CheckConstraint(
            "state IN ('active', 'revoked', 'left')", name="ck_family_memberships_state"
        ),
        sa.CheckConstraint("generation > 0", name="ck_family_memberships_generation"),
        sa.CheckConstraint(
            "(state = 'active' AND ended_at IS NULL) OR "
            "(state IN ('revoked', 'left') AND ended_at IS NOT NULL)",
            name="ck_family_memberships_end_state",
        ),
    )
    op.create_index("ix_family_memberships_user_state", "family_memberships", ["user_id", "state"])
    op.create_index(
        "ix_family_memberships_family_state", "family_memberships", ["family_id", "state"]
    )
    op.create_index(
        "ix_family_memberships_accepted_invitation",
        "family_memberships",
        ["accepted_invitation_id"],
    )

    op.drop_constraint("families_owner_id_fkey", "families", type_="foreignkey")
    op.create_foreign_key(
        "families_owner_id_fkey",
        "families",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.execute(
        """
        CREATE FUNCTION c2a_invitation_identity_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.family_id IS DISTINCT FROM NEW.family_id
             OR OLD.requested_by_user_id IS DISTINCT FROM NEW.requested_by_user_id
             OR OLD.recipient_hash IS DISTINCT FROM NEW.recipient_hash
             OR OLD.recipient_ciphertext IS DISTINCT FROM NEW.recipient_ciphertext
             OR (OLD.recipient_user_id IS NOT NULL
                 AND OLD.recipient_user_id IS DISTINCT FROM NEW.recipient_user_id) THEN
            RAISE EXCEPTION 'Invitation identity is immutable';
          END IF;
          RETURN NEW;
        END;
        $$;
        CREATE TRIGGER c2a_invitation_identity_guard_trigger
        BEFORE UPDATE ON family_invitations
        FOR EACH ROW EXECUTE FUNCTION c2a_invitation_identity_guard();

        CREATE FUNCTION c2a_membership_identity_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.family_id IS DISTINCT FROM NEW.family_id
             OR OLD.user_id IS DISTINCT FROM NEW.user_id
             OR OLD.role IS DISTINCT FROM NEW.role THEN
            RAISE EXCEPTION 'Membership identity is immutable';
          END IF;
          RETURN NEW;
        END;
        $$;
        CREATE TRIGGER c2a_membership_identity_guard_trigger
        BEFORE UPDATE ON family_memberships
        FOR EACH ROW EXECUTE FUNCTION c2a_membership_identity_guard();

        CREATE FUNCTION c2a_idempotency_identity_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.actor_user_id IS DISTINCT FROM NEW.actor_user_id
             OR OLD.operation IS DISTINCT FROM NEW.operation
             OR OLD.idempotency_key IS DISTINCT FROM NEW.idempotency_key
             OR OLD.request_digest IS DISTINCT FROM NEW.request_digest
             OR OLD.state = 'completed' THEN
            RAISE EXCEPTION 'Idempotency command identity is immutable';
          END IF;
          RETURN NEW;
        END;
        $$;
        CREATE TRIGGER c2a_idempotency_identity_guard_trigger
        BEFORE UPDATE ON command_idempotency_records
        FOR EACH ROW EXECUTE FUNCTION c2a_idempotency_identity_guard();
        """
    )


def downgrade():
    connection = op.get_bind()
    has_data = connection.execute(
        sa.text("""
        SELECT EXISTS(SELECT 1 FROM command_idempotency_records)
            OR EXISTS(SELECT 1 FROM family_invitations)
            OR EXISTS(SELECT 1 FROM family_memberships)
        """)
    ).scalar_one()
    if has_data:
        raise RuntimeError("C2A downgrade refused: collaboration or command evidence exists")

    op.execute(
        "DROP TRIGGER IF EXISTS c2a_idempotency_identity_guard_trigger "
        "ON command_idempotency_records"
    )
    op.execute("DROP FUNCTION IF EXISTS c2a_idempotency_identity_guard()")
    op.execute("DROP TRIGGER IF EXISTS c2a_membership_identity_guard_trigger ON family_memberships")
    op.execute("DROP FUNCTION IF EXISTS c2a_membership_identity_guard()")
    op.execute("DROP TRIGGER IF EXISTS c2a_invitation_identity_guard_trigger ON family_invitations")
    op.execute("DROP FUNCTION IF EXISTS c2a_invitation_identity_guard()")

    op.drop_constraint("families_owner_id_fkey", "families", type_="foreignkey")
    op.create_foreign_key(
        "families_owner_id_fkey",
        "families",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_table("family_memberships")
    op.drop_table("family_invitations")
    op.drop_table("command_idempotency_records")
