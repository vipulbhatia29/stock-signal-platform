"""Obs 1b DB+Cache Layer — slow_query, db_pool, migration, cache tables.

Revision ID: a6de25414eb5
Revises: f2a3b4c5d6e7
Create Date: 2026-04-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "a6de25414eb5"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create slow_query_log, db_pool_event, schema_migration_log, cache_operation_log.

    slow_query_log and cache_operation_log are TimescaleDB hypertables with compression.
    db_pool_event and schema_migration_log are regular tables (low volume).
    All tables reside in the observability schema.
    """
    # ------------------------------------------------------------------
    # slow_query_log (hypertable, 1-day chunks, 30d retention)
    # ------------------------------------------------------------------
    op.create_table(
        "slow_query_log",
        sa.Column("id", UUID(as_uuid=False), server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("trace_id", UUID(as_uuid=False), nullable=False),
        sa.Column("span_id", UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", UUID(as_uuid=False), nullable=True),
        sa.Column("session_id", UUID(as_uuid=False), nullable=True),
        sa.Column("query_text", sa.Text, nullable=False),
        sa.Column("query_hash", sa.Text, nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        sa.Column("rows_affected", sa.Integer, nullable=True),
        sa.Column("source_file", sa.Text, nullable=True),
        sa.Column("source_line", sa.Integer, nullable=True),
        sa.Column("env", sa.Text, nullable=False),
        sa.Column("git_sha", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("id", "ts"),
        schema="observability",
    )
    op.create_index(
        "ix_slow_query_log_query_hash",
        "slow_query_log",
        ["query_hash"],
        schema="observability",
    )
    op.execute(
        "SELECT create_hypertable('observability.slow_query_log', 'ts', "
        "chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE)"
    )
    op.execute(
        "ALTER TABLE observability.slow_query_log SET ("
        "timescaledb.compress, "
        "timescaledb.compress_segmentby = 'query_hash'"
        ")"
    )
    op.execute(
        "SELECT add_compression_policy('observability.slow_query_log', "
        "compress_after => INTERVAL '2 days')"
    )

    # ------------------------------------------------------------------
    # db_pool_event (regular table, 90d retention, low volume)
    # ------------------------------------------------------------------
    op.create_table(
        "db_pool_event",
        sa.Column(
            "id",
            UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("trace_id", UUID(as_uuid=False), nullable=False),
        sa.Column("span_id", UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", UUID(as_uuid=False), nullable=True),
        sa.Column("session_id", UUID(as_uuid=False), nullable=True),
        sa.Column("pool_event_type", sa.Text, nullable=False),
        sa.Column("pool_size", sa.Integer, nullable=False),
        sa.Column("checked_out", sa.Integer, nullable=False),
        sa.Column("overflow", sa.Integer, nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("env", sa.Text, nullable=False),
        sa.Column("git_sha", sa.Text, nullable=True),
        schema="observability",
    )

    # ------------------------------------------------------------------
    # schema_migration_log (regular table, 365d retention, low volume)
    # ------------------------------------------------------------------
    op.create_table(
        "schema_migration_log",
        sa.Column(
            "id",
            UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("trace_id", UUID(as_uuid=False), nullable=False),
        sa.Column("span_id", UUID(as_uuid=False), nullable=False),
        sa.Column("migration_id", sa.Text, nullable=False),
        sa.Column("version", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("env", sa.Text, nullable=False),
        sa.Column("git_sha", sa.Text, nullable=True),
        schema="observability",
    )

    # ------------------------------------------------------------------
    # cache_operation_log (hypertable, 6-hour chunks, 7d retention)
    # ------------------------------------------------------------------
    op.create_table(
        "cache_operation_log",
        sa.Column("id", UUID(as_uuid=False), server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("trace_id", UUID(as_uuid=False), nullable=False),
        sa.Column("span_id", UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", UUID(as_uuid=False), nullable=True),
        sa.Column("session_id", UUID(as_uuid=False), nullable=True),
        sa.Column("operation", sa.Text, nullable=False),
        sa.Column("key_pattern", sa.Text, nullable=False),
        sa.Column("hit", sa.Boolean, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("value_bytes", sa.Integer, nullable=True),
        sa.Column("ttl_seconds", sa.Integer, nullable=True),
        sa.Column("error_reason", sa.Text, nullable=True),
        sa.Column("env", sa.Text, nullable=False),
        sa.Column("git_sha", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("id", "ts"),
        schema="observability",
    )
    op.create_index(
        "ix_cache_operation_log_operation",
        "cache_operation_log",
        ["operation"],
        schema="observability",
    )
    op.execute(
        "SELECT create_hypertable('observability.cache_operation_log', 'ts', "
        "chunk_time_interval => INTERVAL '6 hours', if_not_exists => TRUE)"
    )
    op.execute(
        "ALTER TABLE observability.cache_operation_log SET ("
        "timescaledb.compress, "
        "timescaledb.compress_segmentby = 'operation'"
        ")"
    )
    op.execute(
        "SELECT add_compression_policy('observability.cache_operation_log', "
        "compress_after => INTERVAL '1 day')"
    )


def downgrade() -> None:
    """Drop all 4 tables created in this migration."""
    # Hypertables: remove policies before dropping
    op.execute(
        "SELECT remove_compression_policy('observability.cache_operation_log', if_exists => TRUE)"
    )
    op.execute(
        "SELECT remove_compression_policy('observability.slow_query_log', if_exists => TRUE)"
    )
    op.execute("DROP TABLE IF EXISTS observability.cache_operation_log CASCADE")
    op.execute("DROP TABLE IF EXISTS observability.slow_query_log CASCADE")
    op.execute("DROP TABLE IF EXISTS observability.db_pool_event CASCADE")
    op.execute("DROP TABLE IF EXISTS observability.schema_migration_log CASCADE")
