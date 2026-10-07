"""Part 9.5.5-C2B interview participant identity foundation.

Revision ID: d4f8a1c2b3e6
Revises: b7e2c4d891a0
"""

import sqlalchemy as sa
from alembic import op

revision = "d4f8a1c2b3e6"
down_revision = "b7e2c4d891a0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_user_contacts_id_user", "user_contacts", ["id", "user_id"])
    op.create_table(
        "interview_participants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "interview_id",
            sa.Uuid(),
            sa.ForeignKey("interviews.id", ondelete="SET NULL"),
        ),
        sa.Column("interview_scope_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column(
            "family_member_id",
            sa.Uuid(),
            sa.ForeignKey("family_members.id", ondelete="SET NULL"),
        ),
        sa.Column("roles", sa.String(32), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("eligibility_state", sa.String(32), nullable=False),
        sa.Column("verified_contact_id", sa.Uuid()),
        sa.Column("verification_ref", sa.Uuid()),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("adult_declaration_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.BigInteger(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["verified_contact_id", "user_id"],
            ["user_contacts.id", "user_contacts.user_id"],
            name="fk_interview_participants_verified_contact_user",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("roles = 'speaker'", name="ck_interview_participants_roles"),
        sa.CheckConstraint(
            "state IN ('proposed', 'verified', 'inactive', 'disputed')",
            name="ck_interview_participants_state",
        ),
        sa.CheckConstraint(
            "eligibility_state IN ('unknown', 'eligible', 'ineligible')",
            name="ck_interview_participants_eligibility",
        ),
        sa.CheckConstraint(
            "(state = 'proposed' AND eligibility_state = 'unknown') OR "
            "(state = 'verified' AND eligibility_state = 'eligible') OR "
            "(state = 'inactive' AND eligibility_state IN ('eligible', 'ineligible')) OR "
            "state = 'disputed'",
            name="ck_interview_participants_state_eligibility",
        ),
        sa.CheckConstraint(
            "state != 'verified' OR (user_id IS NOT NULL AND verified_contact_id IS NOT NULL "
            "AND verification_ref IS NOT NULL AND verified_at IS NOT NULL "
            "AND adult_declaration_at IS NOT NULL AND eligibility_state = 'eligible')",
            name="ck_interview_participants_verified_evidence",
        ),
        sa.CheckConstraint(
            "state != 'proposed' OR (user_id IS NULL AND verified_contact_id IS NULL "
            "AND verification_ref IS NULL AND verified_at IS NULL "
            "AND adult_declaration_at IS NULL)",
            name="ck_interview_participants_proposed_unclaimed",
        ),
        sa.CheckConstraint("version > 0", name="ck_interview_participants_version"),
        sa.UniqueConstraint("id", "interview_scope_id", name="uq_interview_participants_id_scope"),
    )
    op.create_index(
        "uq_interview_participants_scope_user",
        "interview_participants",
        ["interview_scope_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    for name, columns in (
        ("ix_interview_participants_interview_state", ["interview_id", "state"]),
        ("ix_interview_participants_scope_state", ["interview_scope_id", "state"]),
        ("ix_interview_participants_user_state", ["user_id", "state"]),
        ("ix_interview_participants_family_member", ["family_member_id"]),
    ):
        op.create_index(name, "interview_participants", columns)
    op.execute(
        """
        CREATE FUNCTION c2b_participant_identity_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.interview_scope_id IS DISTINCT FROM NEW.interview_scope_id
             OR OLD.roles IS DISTINCT FROM NEW.roles
             OR (
               OLD.family_member_id IS DISTINCT FROM NEW.family_member_id
               AND NOT (
                 OLD.family_member_id IS NOT NULL
                 AND NEW.family_member_id IS NULL
                 AND NOT EXISTS (
                   SELECT 1 FROM family_members WHERE id = OLD.family_member_id
                 )
               )
             )
             OR (OLD.user_id IS NOT NULL AND OLD.user_id IS DISTINCT FROM NEW.user_id)
             OR (OLD.verified_contact_id IS NOT NULL
                 AND OLD.verified_contact_id IS DISTINCT FROM NEW.verified_contact_id)
             OR (OLD.verification_ref IS NOT NULL
                 AND OLD.verification_ref IS DISTINCT FROM NEW.verification_ref)
             OR (OLD.verified_at IS NOT NULL AND OLD.verified_at IS DISTINCT FROM NEW.verified_at)
             OR (OLD.adult_declaration_at IS NOT NULL
                 AND OLD.adult_declaration_at IS DISTINCT FROM NEW.adult_declaration_at) THEN
            RAISE EXCEPTION 'Participant identity evidence is immutable';
          END IF;
          RETURN NEW;
        END;
        $$;
        CREATE TRIGGER c2b_participant_identity_guard_trigger
        BEFORE UPDATE ON interview_participants
        FOR EACH ROW EXECUTE FUNCTION c2b_participant_identity_guard();
        """
    )


def downgrade():
    connection = op.get_bind()
    if connection.execute(
        sa.text("SELECT EXISTS(SELECT 1 FROM interview_participants)")
    ).scalar_one():
        raise RuntimeError("C2B downgrade refused: participant identity evidence exists")
    op.execute(
        "DROP TRIGGER IF EXISTS c2b_participant_identity_guard_trigger ON interview_participants"
    )
    op.execute("DROP FUNCTION IF EXISTS c2b_participant_identity_guard()")
    op.drop_table("interview_participants")
    op.drop_constraint("uq_user_contacts_id_user", "user_contacts", type_="unique")
