"""Obs 1b Agent Layer — intent_log, reasoning_log, provider_health tables.

Revision ID: ac67ae322af4
Revises: 8dac9bd44fe4
Create Date: 2026-04-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "ac67ae322af4"
down_revision = "8dac9bd44fe4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create agent observability tables.

    agent_intent_log and agent_reasoning_log are regular tables (low volume).
    provider_health_snapshot is a hypertable (high frequency, 60s polling).
    """
    # ------------------------------------------------------------------
    # agent_intent_log (regular table, 30d retention)
    # ------------------------------------------------------------------
    op.create_table(
        "agent_intent_log",
        sa.Column(
            "id",
            UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("trace_id", UUID(as_uuid=False), nullable=False),
        sa.Column("span_id", UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", UUID(as_uuid=False), nullable=True),
        sa.Column("session_id", UUID(as_uuid=False), nullable=True),
        sa.Column("query_id", UUID(as_uuid=False), nullable=True),
        sa.Column("intent", sa.Text, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("out_of_scope", sa.Boolean, nullable=False),
        sa.Column("decline_reason", sa.Text, nullable=True),
        sa.Column("query_text_hash", sa.Text, nullable=False),
        sa.Column("env", sa.Text, nullable=False),
        sa.Column("git_sha", sa.Text, nullable=True),
        schema="observability",
    )
    op.create_index(
        "ix_agent_intent_log_query_id",
        "agent_intent_log",
        ["query_id"],
        schema="observability",
    )

    # ------------------------------------------------------------------
    # agent_reasoning_log (regular table, 30d retention)
    # ------------------------------------------------------------------
    op.create_table(
        "agent_reasoning_log",
        sa.Column(
            "id",
            UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("trace_id", UUID(as_uuid=False), nullable=False),
        sa.Column("span_id", UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", UUID(as_uuid=False), nullable=True),
        sa.Column("session_id", UUID(as_uuid=False), nullable=True),
        sa.Column("query_id", UUID(as_uuid=False), nullable=True),
        sa.Column("loop_step", sa.Integer, nullable=False),
        sa.Column("reasoning_type", sa.Text, nullable=False),
        sa.Column("content_summary", sa.Text, nullable=False),
        sa.Column("tool_calls_proposed", JSONB, nullable=True),
        sa.Column("termination_reason", sa.Text, nullable=True),
        sa.Column("env", sa.Text, nullable=False),
        sa.Column("git_sha", sa.Text, nullable=True),
        schema="observability",
    )
    op.create_index(
        "ix_agent_reasoning_log_query_id_step",
        "agent_reasoning_log",
        ["query_id", "loop_step"],
        schema="observability",
    )

    # ------------------------------------------------------------------
    # provider_health_snapshot (hypertable, 1-hour chunks, 30d retention)
    # ------------------------------------------------------------------
    op.create_table(
        "provider_health_snapshot",
        sa.Column("id", UUID(as_uuid=False), server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("trace_id", UUID(as_uuid=False), nullable=False),
        sa.Column("span_id", UUID(as_uuid=False), nullable=False),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=True),
        sa.Column("is_exhausted", sa.Boolean, nullable=False),
        sa.Column("exhausted_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer, nullable=False),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("env", sa.Text, nullable=False),
        sa.Column("git_sha", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("id", "ts"),
        schema="observability",
    )
    op.create_index(
        "ix_provider_health_snapshot_provider",
        "provider_health_snapshot",
        ["provider"],
        schema="observability",
    )
    op.execute(
        "SELECT create_hypertable('observability.provider_health_snapshot', 'ts', "
        "chunk_time_interval => INTERVAL '1 hour', if_not_exists => TRUE)"
    )
    op.execute(
        "ALTER TABLE observability.provider_health_snapshot SET ("
        "timescaledb.compress, "
        "timescaledb.compress_segmentby = 'provider'"
        ")"
    )
    op.execute(
        "SELECT add_compression_policy('observability.provider_health_snapshot', "
        "compress_after => INTERVAL '1 day')"
    )


def downgrade() -> None:
    """Drop agent layer tables."""
    op.execute(
        "SELECT remove_compression_policy("
        "'observability.provider_health_snapshot', if_exists => TRUE)"
    )
    op.execute("DROP TABLE IF EXISTS observability.provider_health_snapshot CASCADE")
    op.execute("DROP TABLE IF EXISTS observability.agent_reasoning_log CASCADE")
    op.execute("DROP TABLE IF EXISTS observability.agent_intent_log CASCADE")
