"""Synthetic interview agent state and message ordering; SOURCE ONLY, not executed."""

import sqlalchemy as sa
from alembic import op

revision = "f3a96b10d207"
down_revision = "e8c2a9b47106"
branch_labels = None
depends_on = None


def upgrade():
    # Serialize writes during future authorized migration; never renumber source records.
    op.execute("LOCK TABLE interview_messages IN ACCESS EXCLUSIVE MODE")
    duplicate = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM interview_messages GROUP BY session_id, sequence "
                "HAVING count(*) > 1 LIMIT 1"
            )
        )
        .first()
    )
    if duplicate is not None:
        raise RuntimeError("Duplicate legacy message sequences; migration stopped")
    op.create_unique_constraint(
        "uq_interview_messages_session_sequence", "interview_messages", ["session_id", "sequence"]
    )
    op.create_table(
        "interview_agent_states",
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("interview_sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "current_question_message_id",
            sa.Uuid(),
            sa.ForeignKey("interview_messages.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "last_consumed_answer_id",
            sa.Uuid(),
            sa.ForeignKey("interview_messages.id", ondelete="SET NULL"),
        ),
        sa.Column("policy_version", sa.String(100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('idle', 'awaiting_answer', 'ended')", name="ck_agent_status"
        ),
        sa.CheckConstraint("version >= 0", name="ck_agent_version"),
    )
    op.create_table(
        "interview_agent_turns",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("interview_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("request_fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column(
            "input_answer_id",
            sa.Uuid(),
            sa.ForeignKey("interview_messages.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "output_message_id",
            sa.Uuid(),
            sa.ForeignKey("interview_messages.id", ondelete="SET NULL"),
        ),
        sa.Column("question_key", sa.String(100)),
        sa.Column("question_text_normalized", sa.String(120)),
        sa.Column("resulting_version", sa.Integer(), nullable=False),
        sa.Column("resulting_status", sa.String(32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("session_id", "idempotency_key", name="uq_agent_turn_key"),
        sa.UniqueConstraint("input_answer_id", name="uq_agent_consumed_answer"),
        sa.CheckConstraint("action IN ('start', 'answer', 'skip', 'end')", name="ck_agent_action"),
        sa.CheckConstraint("length(request_fingerprint) = 32", name="ck_agent_fingerprint"),
        sa.CheckConstraint("resulting_version > 0", name="ck_agent_turn_version"),
        sa.CheckConstraint(
            "resulting_status IN ('awaiting_answer', 'ended')",
            name="ck_agent_turn_status",
        ),
    )
    op.create_index("ix_interview_agent_turns_session_id", "interview_agent_turns", ["session_id"])


def downgrade():
    op.drop_table("interview_agent_turns")
    op.drop_table("interview_agent_states")
    op.drop_constraint(
        "uq_interview_messages_session_sequence", "interview_messages", type_="unique"
    )
