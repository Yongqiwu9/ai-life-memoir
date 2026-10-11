"""Manual Memory and deterministic Memoir draft slice.

Revision ID: e8c2a9b47106
Revises: d4f8a1c2b3e6
"""

import sqlalchemy as sa
from alembic import op

revision = "e8c2a9b47106"
down_revision = "d4f8a1c2b3e6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "memories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "family_member_id",
            sa.Uuid(),
            sa.ForeignKey("family_members.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "source_message_id",
            sa.Uuid(),
            sa.ForeignKey("interview_messages.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("time_text", sa.String(200)),
        sa.Column("place", sa.String(200)),
        sa.Column("emotion", sa.String(100)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_memories_family_member_id", "memories", ["family_member_id"])
    op.create_index("ix_memories_source_message_id", "memories", ["source_message_id"])
    op.create_table(
        "memoirs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "family_member_id",
            sa.Uuid(),
            sa.ForeignKey("family_members.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("status = 'draft'", name="ck_memoirs_status"),
    )
    op.create_index("ix_memoirs_family_member_id", "memoirs", ["family_member_id"])
    op.create_table(
        "memoir_sections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "memoir_id", sa.Uuid(), sa.ForeignKey("memoirs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "memory_id",
            sa.Uuid(),
            sa.ForeignKey("memories.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.UniqueConstraint("memoir_id", "position", name="uq_memoir_sections_position"),
        sa.UniqueConstraint("memoir_id", "memory_id", name="uq_memoir_sections_memory"),
        sa.CheckConstraint("position > 0", name="ck_memoir_sections_position"),
    )
    op.create_index("ix_memoir_sections_memoir_id", "memoir_sections", ["memoir_id"])
    op.create_index("ix_memoir_sections_memory_id", "memoir_sections", ["memory_id"])


def downgrade():
    op.drop_table("memoir_sections")
    op.drop_table("memoirs")
    op.drop_table("memories")
