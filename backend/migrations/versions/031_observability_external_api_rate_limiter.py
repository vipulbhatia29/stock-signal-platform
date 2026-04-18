"""Observability — external_api_call_log + rate_limiter_event hypertables (Obs 1a PR4).

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-04-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create external_api_call_log and rate_limiter_event TimescaleDB hypertables.

    Both tables live in the observability schema. Compression and retention policies
    are applied after hypertable creation to keep hot data fast and auto-expire old rows.
    """
    # ------------------------------------------------------------------
    # external_api_call_log
    # ------------------------------------------------------------------
    op.create_table(
        "external_api_call_log",
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("trace_id", sa.UUID(), nullable=False),
        sa.Column("span_id", sa.UUID(), nullable=False),
        sa.Column("parent_span_id", sa.UUID(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("error_reason", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("request_bytes", sa.Integer(), nullable=True),
        sa.Column("response_bytes", sa.Integer(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=True, server_default=sa.text("0")),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("rate_limit_remaining", sa.Integer(), nullable=True),
        sa.Column("rate_limit_reset_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rate_limit_headers", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("stack_signature", sa.Text(), nullable=True),
        sa.Column("stack_hash", sa.CHAR(64), nullable=True),
        sa.Column("env", sa.Text(), nullable=False),
        sa.Column("git_sha", sa.Text(), nullable=True),
        schema="observability",
    )

    # Convert to TimescaleDB hypertable partitioned by ts (1-day chunks)
    op.execute(
        sa.text(
            "SELECT create_hypertable("
            "  'observability.external_api_call_log',"
            "  'ts',"
            "  chunk_time_interval => INTERVAL '1 day',"
            "  if_not_exists => TRUE"
            ")"
        )
    )

    # Indexes
    op.create_index(
        "ix_ext_api_call_log_trace_id",
        "external_api_call_log",
        ["trace_id"],
        schema="observability",
    )
    op.create_index(
        "ix_ext_api_call_log_provider_ts",
        "external_api_call_log",
        ["provider", sa.text("ts DESC")],
        schema="observability",
    )
    op.execute(
        sa.text(
            "CREATE INDEX ix_ext_api_call_log_error_reason_ts "
            "ON observability.external_api_call_log (error_reason, ts DESC) "
            "WHERE error_reason IS NOT NULL"
        )
    )

    # Compression: orderby ts DESC, segmentby provider, after 7 days
    op.execute(
        sa.text(
            "ALTER TABLE observability.external_api_call_log "
            "SET ("
            "  timescaledb.compress,"
            "  timescaledb.compress_orderby = 'ts DESC',"
            "  timescaledb.compress_segmentby = 'provider'"
            ")"
        )
    )
    op.execute(
        sa.text(
            "SELECT add_compression_policy("
            "  'observability.external_api_call_log',"
            "  INTERVAL '7 days'"
            ")"
        )
    )

    # Retention: 30 days
    op.execute(
        sa.text(
            "SELECT add_retention_policy("
            "  'observability.external_api_call_log',"
            "  INTERVAL '30 days'"
            ")"
        )
    )

    # ------------------------------------------------------------------
    # rate_limiter_event
    # ------------------------------------------------------------------
    op.create_table(
        "rate_limiter_event",
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("trace_id", sa.UUID(), nullable=True),
        sa.Column("span_id", sa.UUID(), nullable=True),
        sa.Column("limiter_name", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("wait_time_ms", sa.Integer(), nullable=True),
        sa.Column("tokens_remaining", sa.Integer(), nullable=True),
        sa.Column("reason_if_fallback", sa.Text(), nullable=True),
        sa.Column("env", sa.Text(), nullable=False),
        sa.Column("git_sha", sa.Text(), nullable=True),
        schema="observability",
    )

    # Convert to TimescaleDB hypertable partitioned by ts (1-day chunks)
    op.execute(
        sa.text(
            "SELECT create_hypertable("
            "  'observability.rate_limiter_event',"
            "  'ts',"
            "  chunk_time_interval => INTERVAL '1 day',"
            "  if_not_exists => TRUE"
            ")"
        )
    )

    # Index: (limiter_name, action, ts DESC)
    op.create_index(
        "ix_rate_limiter_event_limiter_action_ts",
        "rate_limiter_event",
        ["limiter_name", "action", sa.text("ts DESC")],
        schema="observability",
    )

    # Retention: 30 days
    op.execute(
        sa.text(
            "SELECT add_retention_policy(  'observability.rate_limiter_event',  INTERVAL '30 days')"
        )
    )


def downgrade() -> None:
    """Remove retention/compression policies before dropping tables.

    TimescaleDB requires policies to be removed before table drop to avoid
    orphaned background jobs.
    """
    # Remove policies for external_api_call_log
    _ext_table = "observability.external_api_call_log"
    op.execute(sa.text(f"SELECT remove_retention_policy('{_ext_table}', if_exists => TRUE)"))
    op.execute(sa.text(f"SELECT remove_compression_policy('{_ext_table}', if_exists => TRUE)"))

    # Remove policies for rate_limiter_event
    op.execute(
        sa.text(
            "SELECT remove_retention_policy('observability.rate_limiter_event', if_exists => TRUE)"
        )
    )

    # Drop tables (hypertable + chunks cascade automatically)
    op.drop_table("external_api_call_log", schema="observability")
    op.drop_table("rate_limiter_event", schema="observability")
