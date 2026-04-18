"""obs_1b_http_layer

Revision ID: 44fdf1e09f76
Revises: d5e6f7a8b9c0
Create Date: 2026-04-18
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID

revision = "44fdf1e09f76"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create request_log and api_error_log hypertables in observability schema."""
    # --- request_log ---
    op.create_table(
        "request_log",
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("trace_id", UUID, nullable=False),
        sa.Column("span_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=True),
        sa.Column("session_id", UUID, nullable=True),
        sa.Column("method", sa.Text, nullable=False),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("raw_path", sa.Text, nullable=False),
        sa.Column("status_code", sa.Integer, nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("request_bytes", sa.Integer, nullable=True),
        sa.Column("response_bytes", sa.Integer, nullable=True),
        sa.Column("ip_address", INET, nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("referer", sa.Text, nullable=True),
        sa.Column("environment_snapshot", JSONB, nullable=True),
        sa.Column("env", sa.Text, nullable=False),
        sa.Column("git_sha", sa.Text, nullable=True),
        schema="observability",
    )
    op.execute(
        sa.text(
            "SELECT create_hypertable('observability.request_log', 'ts', "
            "chunk_time_interval => INTERVAL '1 day')"
        )
    )
    op.create_index("ix_request_log_trace_id", "request_log", ["trace_id"], schema="observability")
    op.create_index(
        "ix_request_log_user_ts",
        "request_log",
        ["user_id", sa.text("ts DESC")],
        schema="observability",
    )
    op.create_index(
        "ix_request_log_errors",
        "request_log",
        ["status_code", sa.text("ts DESC")],
        schema="observability",
        postgresql_where=sa.text("status_code >= 400"),
    )
    op.create_index(
        "ix_request_log_path_ts",
        "request_log",
        ["path", sa.text("ts DESC")],
        schema="observability",
    )

    # Compression: after 1 day, segmentby path
    # Retention via Celery beat task (not TimescaleDB policy — project pattern)
    op.execute(
        sa.text(
            "ALTER TABLE observability.request_log SET ("
            "  timescaledb.compress,"
            "  timescaledb.compress_segmentby = 'path'"
            ")"
        )
    )
    op.execute(
        sa.text("SELECT add_compression_policy('observability.request_log', INTERVAL '1 day')")
    )

    # --- api_error_log ---
    op.create_table(
        "api_error_log",
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("trace_id", UUID, nullable=False),
        sa.Column("span_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=True),
        sa.Column("status_code", sa.Integer, nullable=False),
        sa.Column("error_type", sa.Text, nullable=False),
        sa.Column("error_reason", sa.Text, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("stack_signature", sa.Text, nullable=True),
        sa.Column("stack_hash", sa.String(64), nullable=True),
        sa.Column("stack_trace", sa.Text, nullable=True),
        sa.Column("exception_class", sa.Text, nullable=True),
        sa.Column("env", sa.Text, nullable=False),
        sa.Column("git_sha", sa.Text, nullable=True),
        schema="observability",
    )
    op.execute(
        sa.text(
            "SELECT create_hypertable('observability.api_error_log', 'ts', "
            "chunk_time_interval => INTERVAL '1 day')"
        )
    )
    op.create_index(
        "ix_api_error_log_trace_id", "api_error_log", ["trace_id"], schema="observability"
    )
    op.create_index(
        "ix_api_error_log_status_ts",
        "api_error_log",
        ["status_code", sa.text("ts DESC")],
        schema="observability",
    )
    op.create_index(
        "ix_api_error_log_stack_hash", "api_error_log", ["stack_hash"], schema="observability"
    )

    # Retention via Celery beat task (not TimescaleDB policy — project pattern)
    op.execute(
        sa.text(
            "ALTER TABLE observability.api_error_log SET ("
            "  timescaledb.compress,"
            "  timescaledb.compress_segmentby = 'error_type'"
            ")"
        )
    )
    op.execute(
        sa.text("SELECT add_compression_policy('observability.api_error_log', INTERVAL '1 day')")
    )


def downgrade() -> None:
    """Drop request_log and api_error_log hypertables from observability schema."""
    op.execute(
        sa.text(
            "SELECT remove_compression_policy('observability.api_error_log', if_exists => true)"
        )
    )
    op.drop_table("api_error_log", schema="observability")

    op.execute(
        sa.text("SELECT remove_compression_policy('observability.request_log', if_exists => true)")
    )
    op.drop_table("request_log", schema="observability")
