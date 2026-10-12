"""Offline Provider Extension schema contract; SOURCE ONLY, not executed."""

import sqlalchemy as sa
from alembic import op

revision = "a196e4c72b08"
down_revision = "f3a96b10d207"
branch_labels = None
depends_on = None

# Kept self-contained: migrations must not import mutable application ORM code.
V1 = "interview-agent.v1"
V2 = "interview-agent.v2"

# CHECKs explicitly handle NULL; SQL UNKNOWN must not admit incomplete v2 results.
# JSON shape/ordering and write-once semantics remain Schema/Service-only rules.
STATE_CHECKS = (
    ("ck_agent_contract", f"contract_version IN ('{V1}', '{V2}')"),
    (
        "ck_agent_status",
        (
            f"(contract_version = '{V1}' AND status IN ('idle', 'awaiting_answer', 'ended')) "
            f"OR (contract_version = '{V2}' AND status IN ('idle', 'listening', 'paused', 'ended'))"
        ),
    ),
    ("ck_agent_version", "version >= 0"),
    ("ck_agent_epoch", "generation_epoch >= 0"),
    ("ck_agent_v2_answer", f"contract_version = '{V1}' OR last_consumed_answer_id IS NULL"),
)

_EMPTY_RESULT = (
    "result_kind IS NULL AND result_state_contract_version IS NULL "
    "AND resulting_version IS NULL AND resulting_status IS NULL "
    "AND output_message_id IS NULL AND output_scope_id IS NULL AND question_key IS NULL"
)
_RESULT_SNAPSHOT = (
    "result_kind IS NOT NULL AND result_state_contract_version IS NOT NULL "
    "AND resulting_version IS NOT NULL AND resulting_status IS NOT NULL"
)
TURN_CHECKS = (
    ("ck_agent_turn_contract", f"contract_version IN ('{V1}', '{V2}')"),
    (
        "ck_agent_action",
        (
            f"(contract_version = '{V1}' AND action IN ('start', 'answer', 'skip', 'end')) "
            f"OR (contract_version = '{V2}' "
            "AND action IN ('start', 'request_question', 'pause', 'resume', 'end'))"
        ),
    ),
    ("ck_agent_fingerprint", "length(request_fingerprint) = 32"),
    (
        "ck_agent_execution",
        "execution_status IN ('pending', 'completed', 'failed', 'discarded')",
    ),
    ("ck_agent_reserved_version", "reserved_version IS NULL OR reserved_version >= 0"),
    ("ck_agent_reserved_epoch", "reserved_epoch IS NULL OR reserved_epoch >= 0"),
    ("ck_agent_turn_version", "resulting_version IS NULL OR resulting_version >= 0"),
    (
        "ck_agent_turn_status",
        (
            "(result_state_contract_version IS NULL AND resulting_status IS NULL) "
            f"OR (result_state_contract_version = '{V1}' AND resulting_status IS NOT NULL "
            "AND resulting_status IN ('idle', 'awaiting_answer', 'ended')) "
            f"OR (result_state_contract_version = '{V2}' AND resulting_status IS NOT NULL "
            "AND resulting_status IN ('idle', 'listening', 'paused', 'ended'))"
        ),
    ),
    (
        "ck_agent_turn_version_fields",
        (
            f"(contract_version = '{V1}' AND reserved_version IS NULL AND reserved_epoch IS NULL "
            "AND context_present IS NULL AND context_message_id IS NULL AND context_scope_id IS NULL "
            "AND asked_question_message_ids IS NULL AND provider_id IS NULL) "
            f"OR (contract_version = '{V2}' AND reserved_version IS NOT NULL "
            "AND reserved_epoch IS NOT NULL AND context_present IS NOT NULL "
            "AND asked_question_message_ids IS NOT NULL AND input_answer_id IS NULL "
            "AND question_text_normalized IS NULL)"
        ),
    ),
    (
        "ck_agent_context",
        (
            f"contract_version = '{V1}' OR "
            "(context_present = false AND context_message_id IS NULL AND context_scope_id IS NULL) "
            "OR (context_present = true AND context_scope_id IS NOT NULL "
            "AND (context_message_id IS NULL OR context_message_id = context_scope_id))"
        ),
    ),
    (
        "ck_agent_output_scope",
        (
            "output_message_id IS NULL OR "
            "(output_scope_id IS NOT NULL AND output_message_id = output_scope_id)"
        ),
    ),
    (
        "ck_agent_turn_lifecycle",
        (
            f"(contract_version = '{V1}' AND execution_status = 'completed' "
            f"AND {_RESULT_SNAPSHOT} AND result_state_contract_version = '{V1}' "
            "AND resulting_version > 0 AND resulting_status IN ('awaiting_answer', 'ended') "
            "AND result_kind IN ('control', 'question', 'no_question') "
            "AND failure_code IS NULL AND discard_reason IS NULL) "
            f"OR (contract_version = '{V2}' AND ("
            "(execution_status = 'pending' AND action = 'request_question' AND provider_id IS NOT NULL "
            f"AND {_EMPTY_RESULT} AND failure_code IS NULL AND discard_reason IS NULL "
            "AND finished_at IS NULL) OR "
            "(execution_status = 'failed' AND action = 'request_question' AND provider_id IS NOT NULL "
            f"AND {_EMPTY_RESULT} AND failure_code IS NOT NULL AND discard_reason IS NULL "
            "AND finished_at IS NOT NULL) OR "
            "(execution_status = 'discarded' AND action = 'request_question' "
            f"AND provider_id IS NOT NULL AND {_EMPTY_RESULT} AND failure_code IS NULL "
            "AND discard_reason IS NOT NULL AND finished_at IS NOT NULL) OR "
            f"(execution_status = 'completed' AND {_RESULT_SNAPSHOT} "
            "AND finished_at IS NOT NULL AND failure_code IS NULL AND discard_reason IS NULL "
            "AND ((result_kind = 'control' AND action IN ('start', 'pause', 'resume', 'end') "
            "AND provider_id IS NULL AND context_present = false AND context_message_id IS NULL "
            "AND context_scope_id IS NULL AND output_message_id IS NULL AND output_scope_id IS NULL "
            "AND question_key IS NULL "
            f"AND (result_state_contract_version = '{V2}' "
            f"OR (action = 'end' AND result_state_contract_version = '{V1}' "
            "AND resulting_status = 'ended'))) OR "
            "(result_kind = 'question' AND action = 'request_question' AND provider_id IS NOT NULL "
            "AND question_key IS NOT NULL AND output_scope_id IS NOT NULL "
            f"AND result_state_contract_version = '{V2}' AND resulting_status = 'listening') OR "
            "(result_kind = 'no_question' AND action = 'request_question' AND provider_id IS NOT NULL "
            "AND question_key IS NULL AND output_message_id IS NULL AND output_scope_id IS NULL "
            f"AND result_state_contract_version = '{V2}' AND resulting_status = 'listening')))"
            "))"
        ),
    ),
)


STATE_COLUMNS = (
    sa.Column("contract_version", sa.String(32), nullable=True),
    sa.Column("generation_epoch", sa.BigInteger(), nullable=True),
)
TURN_COLUMNS = (
    sa.Column("contract_version", sa.String(32), nullable=True),
    sa.Column("reserved_version", sa.Integer(), nullable=True),
    sa.Column("reserved_epoch", sa.BigInteger(), nullable=True),
    sa.Column("execution_status", sa.String(32), nullable=True),
    sa.Column("context_present", sa.Boolean(), nullable=True),
    sa.Column("context_message_id", sa.Uuid(), nullable=True),
    sa.Column("context_scope_id", sa.Uuid(), nullable=True),
    sa.Column("asked_question_message_ids", sa.JSON(none_as_null=True), nullable=True),
    sa.Column("provider_id", sa.String(64), nullable=True),
    sa.Column("output_scope_id", sa.Uuid(), nullable=True),
    sa.Column("result_kind", sa.String(32), nullable=True),
    sa.Column("result_state_contract_version", sa.String(32), nullable=True),
    sa.Column("failure_code", sa.String(64), nullable=True),
    sa.Column("discard_reason", sa.String(64), nullable=True),
    sa.Column(
        "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True
    ),
    sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
)


def upgrade():
    op.execute("LOCK TABLE interview_agent_states, interview_agent_turns IN ACCESS EXCLUSIVE MODE")
    op.drop_constraint("ck_agent_status", "interview_agent_states", type_="check")
    for name in ("ck_agent_action", "ck_agent_turn_version", "ck_agent_turn_status"):
        op.drop_constraint(name, "interview_agent_turns", type_="check")
    for column in STATE_COLUMNS:
        op.add_column("interview_agent_states", column)
    for column in TURN_COLUMNS:
        op.add_column("interview_agent_turns", column)

    # Preserve legacy status/version/intent. Zero initializes the new epoch counter;
    # it does not certify historical source identity or authorization.
    op.execute(
        sa.text(
            "UPDATE interview_agent_states "
            "SET contract_version = 'interview-agent.v1', generation_epoch = 0"
        )
    )
    # M01 may already have nulled the live output FK. A surviving question key,
    # normalized legacy text or awaiting_answer snapshot still records output intent.
    # Only known live IDs are copied. No missing output ID or completion time is invented.
    # updated_at starts at its known created_at; it is not historical completion evidence.
    op.execute(
        sa.text(
            "UPDATE interview_agent_turns SET "
            "contract_version = 'interview-agent.v1', execution_status = 'completed', "
            "result_state_contract_version = 'interview-agent.v1', "
            "output_scope_id = output_message_id, updated_at = created_at, "
            "result_kind = CASE WHEN action = 'end' THEN 'control' "
            "WHEN output_message_id IS NOT NULL OR question_key IS NOT NULL "
            "OR question_text_normalized IS NOT NULL OR resulting_status = 'awaiting_answer' "
            "THEN 'question' ELSE 'no_question' END"
        )
    )
    op.alter_column("interview_agent_states", "contract_version", nullable=False)
    op.alter_column("interview_agent_states", "generation_epoch", nullable=False)
    for name in ("contract_version", "execution_status", "updated_at"):
        op.alter_column("interview_agent_turns", name, nullable=False)
    for name in ("resulting_version", "resulting_status"):
        op.alter_column("interview_agent_turns", name, nullable=True)
    op.create_foreign_key(
        "fk_agent_context_message",
        "interview_agent_turns",
        "interview_messages",
        ["context_message_id"],
        ["id"],
        ondelete="SET NULL",
    )
    for name, sql in STATE_CHECKS:
        if name != "ck_agent_version":
            op.create_check_constraint(name, "interview_agent_states", sql)
    for name, sql in TURN_CHECKS:
        if name != "ck_agent_fingerprint":
            op.create_check_constraint(name, "interview_agent_turns", sql)
    op.create_index(
        "uq_agent_pending_session",
        "interview_agent_turns",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text("execution_status = 'pending'"),
    )
    op.create_index(
        "uq_agent_v2_output_scope",
        "interview_agent_turns",
        ["output_scope_id"],
        unique=True,
        postgresql_where=sa.text(
            "contract_version = 'interview-agent.v2' AND output_scope_id IS NOT NULL"
        ),
    )
    op.create_index("ix_agent_context_message", "interview_agent_turns", ["context_message_id"])
    op.create_index(
        "ix_agent_session_execution", "interview_agent_turns", ["session_id", "execution_status"]
    )


def downgrade():
    # Take the writer lock before checking: never race with a new v2 reserve/control.
    op.execute("LOCK TABLE interview_agent_states, interview_agent_turns IN ACCESS EXCLUSIVE MODE")
    has_v2 = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM interview_agent_states WHERE contract_version = 'interview-agent.v2' "
                "UNION ALL SELECT 1 FROM interview_agent_turns "
                "WHERE contract_version = 'interview-agent.v2' LIMIT 1"
            )
        )
        .first()
    )
    if has_v2 is not None:
        raise RuntimeError("Provider extension downgrade requires a separate data rollback plan")

    # No data deletion or Session reopening. All remaining rows are legacy v1.
    for name in (
        "uq_agent_pending_session",
        "uq_agent_v2_output_scope",
        "ix_agent_context_message",
        "ix_agent_session_execution",
    ):
        op.drop_index(name, table_name="interview_agent_turns")
    for name, _ in TURN_CHECKS:
        if name != "ck_agent_fingerprint":
            op.drop_constraint(name, "interview_agent_turns", type_="check")
    for name, _ in STATE_CHECKS:
        if name != "ck_agent_version":
            op.drop_constraint(name, "interview_agent_states", type_="check")
    op.drop_constraint("fk_agent_context_message", "interview_agent_turns", type_="foreignkey")
    for name in ("resulting_version", "resulting_status"):
        op.alter_column("interview_agent_turns", name, nullable=False)
    for column in reversed(TURN_COLUMNS):
        op.drop_column("interview_agent_turns", column.name)
    for column in reversed(STATE_COLUMNS):
        op.drop_column("interview_agent_states", column.name)
    op.create_check_constraint(
        "ck_agent_status",
        "interview_agent_states",
        "status IN ('idle', 'awaiting_answer', 'ended')",
    )
    op.create_check_constraint(
        "ck_agent_action", "interview_agent_turns", "action IN ('start', 'answer', 'skip', 'end')"
    )
    op.create_check_constraint(
        "ck_agent_turn_version", "interview_agent_turns", "resulting_version > 0"
    )
    op.create_check_constraint(
        "ck_agent_turn_status",
        "interview_agent_turns",
        "resulting_status IN ('awaiting_answer', 'ended')",
    )
