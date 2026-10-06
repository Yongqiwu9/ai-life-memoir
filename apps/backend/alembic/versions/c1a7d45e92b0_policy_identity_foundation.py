"""Part 9.5.5-C1 Policy and single-principal identity foundation.

Revision ID: c1a7d45e92b0
Revises: adf9c60d178d
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c1a7d45e92b0"
down_revision = "adf9c60d178d"
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
    op.add_column(
        "users",
        sa.Column("principal_kind", sa.String(32), server_default="account", nullable=False),
    )
    op.add_column(
        "users", sa.Column("auth_generation", sa.BigInteger(), server_default="1", nullable=False)
    )
    op.alter_column("users", "email", existing_type=sa.String(320), nullable=True)
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=True)
    op.create_check_constraint(
        "ck_users_principal_kind", "users", "principal_kind IN ('account', 'rights_only', 'system')"
    )
    op.create_check_constraint("ck_users_auth_generation", "users", "auth_generation > 0")
    op.create_check_constraint(
        "ck_users_credentials",
        "users",
        "(principal_kind = 'account' AND email IS NOT NULL AND length(trim(email)) > 3 "
        "AND email LIKE '%@%' AND password_hash IS NOT NULL AND length(password_hash) > 0) "
        "OR (principal_kind IN ('rights_only', 'system') AND email IS NULL AND password_hash IS NULL)",
    )
    # Defaults backfill existing account principals only. No Contact/Speaker/Consent inference.
    op.create_table(
        "privacy_policy_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("version", sa.String(100), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("parameters", postgresql.JSONB(), nullable=False),
        sa.Column("notices", postgresql.JSONB(), nullable=False),
        sa.Column("capabilities", postgresql.JSONB(), nullable=False),
        sa.Column("digest", sa.LargeBinary(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.UniqueConstraint("version"),
        sa.UniqueConstraint("digest"),
        sa.CheckConstraint(
            "state IN ('draft', 'active', 'retired')", name="ck_privacy_policy_state"
        ),
        sa.CheckConstraint("length(digest) = 32", name="ck_privacy_policy_digest"),
        sa.CheckConstraint(
            "(state = 'draft' AND published_at IS NULL) OR (state IN ('active', 'retired') AND published_at IS NOT NULL)",
            name="ck_privacy_policy_published",
        ),
    )
    op.create_index(
        "uq_privacy_policy_active",
        "privacy_policy_versions",
        ["state"],
        unique=True,
        postgresql_where=sa.text("state = 'active'"),
    )
    op.create_table(
        "user_contacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("value_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("lookup_hash", sa.LargeBinary(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.CheckConstraint("kind IN ('email', 'phone')", name="ck_user_contact_kind"),
        sa.CheckConstraint(
            "state IN ('pending', 'verified', 'revoked', 'legacy_unverified')",
            name="ck_user_contact_state",
        ),
        sa.CheckConstraint(
            "length(value_ciphertext) > 0 AND length(lookup_hash) = 32",
            name="ck_user_contact_storage",
        ),
        sa.CheckConstraint(
            "state != 'verified' OR verified_at IS NOT NULL", name="ck_user_contact_verified"
        ),
        sa.CheckConstraint(
            "state != 'revoked' OR revoked_at IS NOT NULL", name="ck_user_contact_revoked"
        ),
    )
    for column in ("user_id", "verified_at", "revoked_at"):
        op.create_index("ix_user_contacts_" + column, "user_contacts", [column])
    op.create_index(
        "uq_user_contact_effective_channel",
        "user_contacts",
        ["kind", "lookup_hash"],
        unique=True,
        postgresql_where=sa.text("state IN ('pending', 'verified')"),
    )
    op.create_table(
        "auth_challenges",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("context_kind", sa.String(64), nullable=False),
        sa.Column("context_id", sa.Uuid()),
        sa.Column("channel_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("channel_hash", sa.LargeBinary(), nullable=False),
        sa.Column("code_digest", sa.LargeBinary(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "state IN ('pending', 'verified', 'consumed', 'expired', 'locked')",
            name="ck_auth_challenge_state",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_auth_challenge_attempt_count"),
        sa.CheckConstraint(
            "length(code_digest) = 32 AND length(channel_hash) = 32 AND length(channel_ciphertext) > 0",
            name="ck_auth_challenge_storage",
        ),
        sa.CheckConstraint(
            "state != 'consumed' OR (consumed_at IS NOT NULL AND user_id IS NOT NULL)",
            name="ck_auth_challenge_consumed",
        ),
    )
    for column in ("user_id", "expires_at"):
        op.create_index("ix_auth_challenges_" + column, "auth_challenges", [column])
    op.execute("""
        CREATE FUNCTION c1_policy_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE k text;
        BEGIN
          IF TG_OP = 'DELETE' THEN
            IF OLD.published_at IS NOT NULL THEN
              RAISE EXCEPTION 'Published policy is immutable';
            END IF;
            RETURN OLD;
          END IF;
          IF TG_OP = 'UPDATE' AND OLD.published_at IS NOT NULL THEN
            IF ROW(NEW.version, NEW.parameters, NEW.notices, NEW.capabilities, NEW.digest, NEW.published_at)
               IS DISTINCT FROM ROW(OLD.version, OLD.parameters, OLD.notices, OLD.capabilities, OLD.digest, OLD.published_at)
               OR (NEW.state IS DISTINCT FROM OLD.state AND NOT (OLD.state = 'active' AND NEW.state = 'retired')) THEN
              RAISE EXCEPTION 'Published policy is immutable';
            END IF;
          END IF;
          IF NEW.state IN ('active', 'retired') THEN
            FOREACH k IN ARRAY ARRAY['sanitization_review_window', 'online_deletion_deadline',
              'third_party_deletion_deadline', 'backup_retention_window', 'object_version_retention_window',
              'database_recovery_retention_window', 'withdrawal_quarantine_retention',
              'deletion_ledger_retention', 'sanitization_evidence_retention', 'invitation_window',
              'auth_challenge_window', 'rights_token_window', 'high_risk_reverification_window', 'late_job_window'] LOOP
              IF jsonb_typeof(NEW.parameters->k->'seconds') IS DISTINCT FROM 'number'
                 OR NOT coalesce((NEW.parameters->k->>'seconds') ~ '^[0-9]+$', false)
                 OR (NEW.parameters->k->>'seconds')::numeric <= 0 THEN
                RAISE EXCEPTION 'Policy parameters incomplete';
              END IF;
            END LOOP;
            IF jsonb_typeof(NEW.parameters->'sanitization_retry_limit') IS DISTINCT FROM 'number'
               OR NOT coalesce((NEW.parameters->>'sanitization_retry_limit') ~ '^[0-9]+$', false) THEN
              RAISE EXCEPTION 'Policy retry limit invalid';
            END IF;
            FOREACH k IN ARRAY ARRAY['recording', 'transcription', 'ai_analysis', 'family_share', 'retention'] LOOP
              IF jsonb_typeof(NEW.notices->k) IS DISTINCT FROM 'string' OR length(trim(NEW.notices->>k)) = 0 THEN
                RAISE EXCEPTION 'Policy notices incomplete';
              END IF;
            END LOOP;
            FOREACH k IN ARRAY ARRAY['capture', 'consent', 'source_restore', 'sanitization_publish', 'external_processing'] LOOP
              IF NEW.capabilities->k->'verified' IS DISTINCT FROM 'true'::jsonb
                 OR NEW.capabilities->k->>'evidence_ref' IS NULL THEN
                RAISE EXCEPTION 'Policy capabilities unverified';
              END IF;
              PERFORM (NEW.capabilities->k->>'evidence_ref')::uuid;
            END LOOP;
            IF (NEW.parameters->'sanitization_review_window'->>'seconds')::numeric >
               (NEW.parameters->'online_deletion_deadline'->>'seconds')::numeric THEN
              RAISE EXCEPTION 'Sanitization exceeds deletion deadline';
            END IF;
            FOREACH k IN ARRAY ARRAY['backup_retention_window', 'object_version_retention_window', 'database_recovery_retention_window', 'late_job_window'] LOOP
              IF (NEW.parameters->'deletion_ledger_retention'->>'seconds')::numeric <
                 (NEW.parameters->k->>'seconds')::numeric THEN
                RAISE EXCEPTION 'Ledger recovery coverage incomplete';
              END IF;
            END LOOP;
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER c1_policy_guard_trigger BEFORE INSERT OR UPDATE OR DELETE
        ON privacy_policy_versions FOR EACH ROW EXECUTE FUNCTION c1_policy_guard();
    """)
    op.execute("""
        CREATE FUNCTION c1_challenge_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF ROW(NEW.context_kind, NEW.context_id, NEW.channel_ciphertext, NEW.channel_hash, NEW.code_digest, NEW.expires_at)
             IS DISTINCT FROM ROW(OLD.context_kind, OLD.context_id, OLD.channel_ciphertext, OLD.channel_hash, OLD.code_digest, OLD.expires_at) THEN
            RAISE EXCEPTION 'Challenge context is immutable';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER c1_challenge_guard_trigger BEFORE UPDATE ON auth_challenges
        FOR EACH ROW EXECUTE FUNCTION c1_challenge_guard();
    """)


def downgrade():
    connection = op.get_bind()
    unsafe = connection.execute(
        sa.text("""
        SELECT EXISTS(SELECT 1 FROM users WHERE principal_kind != 'account' OR auth_generation != 1)
            OR EXISTS(SELECT 1 FROM privacy_policy_versions)
            OR EXISTS(SELECT 1 FROM user_contacts)
            OR EXISTS(SELECT 1 FROM auth_challenges)
    """)
    ).scalar_one()
    if unsafe:
        raise RuntimeError(
            "C1 downgrade refused: identity or privacy evidence exists; use forward repair"
        )
    op.execute("DROP TRIGGER c1_challenge_guard_trigger ON auth_challenges")
    op.execute("DROP FUNCTION c1_challenge_guard()")
    op.execute("DROP TRIGGER c1_policy_guard_trigger ON privacy_policy_versions")
    op.execute("DROP FUNCTION c1_policy_guard()")
    op.drop_table("auth_challenges")
    op.drop_table("user_contacts")
    op.drop_table("privacy_policy_versions")
    for name in ("ck_users_credentials", "ck_users_auth_generation", "ck_users_principal_kind"):
        op.drop_constraint(name, "users", type_="check")
    op.alter_column("users", "email", existing_type=sa.String(320), nullable=False)
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=False)
    op.drop_column("users", "auth_generation")
    op.drop_column("users", "principal_kind")
