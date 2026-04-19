"""Obs 1b Celery Layer — heartbeat, beat_schedule, queue_depth tables.

Revision ID: 8dac9bd44fe4
Revises: a6de25414eb5
Create Date: 2026-04-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "8dac9bd44fe4"
down_revision = "a6de25414eb5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create celery observability tables and extend pipeline_runs.

    celery_worker_heartbeat and celery_queue_depth are TimescaleDB hypertables
    (high-frequency, short retention). beat_schedule_run is a regular table
    (low volume). Also adds nullable trace_id to pipeline_runs for correlation.
    """
    # ------------------------------------------------------------------
    # celery_worker_heartbeat (hypertable, 1-hour chunks, 7d retention)
    # ------------------------------------------------------------------
    op.create_table(
        "celery_worker_heartbeat",
        sa.Column("id", UUID(as_uuid=False), server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("trace_id", UUID(as_uuid=False), nullable=False),
        sa.Column("span_id", UUID(as_uuid=False), nullable=False),
        sa.Column("worker_name", sa.Text, nullable=False),
        sa.Column("hostname", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("tasks_in_flight", sa.Integer, nullable=False),
        sa.Column("queue_names", JSONB, nullable=False),
        sa.Column("uptime_seconds", sa.Integer, nullable=False),
        sa.Column("env", sa.Text, nullable=False),
        sa.Column("git_sha", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("id", "ts"),
        schema="observability",
    )
    op.create_index(
        "ix_celery_worker_heartbeat_worker_name",
        "celery_worker_heartbeat",
        ["worker_name"],
        schema="observability",
    )
    op.execute(
        "SELECT create_hypertable('observability.celery_worker_heartbeat', 'ts', "
        "chunk_time_interval => INTERVAL '1 hour', if_not_exists => TRUE)"
    )
    op.execute(
        "ALTER TABLE observability.celery_worker_heartbeat SET ("
        "timescaledb.compress, "
        "timescaledb.compress_segmentby = 'worker_name'"
        ")"
    )
    op.execute(
        "SELECT add_compression_policy('observability.celery_worker_heartbeat', "
        "compress_after => INTERVAL '1 day')"
    )

    # ------------------------------------------------------------------
    # beat_schedule_run (regular table, 90d retention, low volume)
    # ------------------------------------------------------------------
    op.create_table(
        "beat_schedule_run",
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
        sa.Column("task_name", sa.Text, nullable=False),
        sa.Column("scheduled_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual_start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("drift_seconds", sa.Float, nullable=False),
        sa.Column("outcome", sa.Text, nullable=False),
        sa.Column("error_reason", sa.Text, nullable=True),
        sa.Column("env", sa.Text, nullable=False),
        sa.Column("git_sha", sa.Text, nullable=True),
        schema="observability",
    )

    # ------------------------------------------------------------------
    # celery_queue_depth (hypertable, 1-hour chunks, 7d retention)
    # ------------------------------------------------------------------
    op.create_table(
        "celery_queue_depth",
        sa.Column("id", UUID(as_uuid=False), server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("trace_id", UUID(as_uuid=False), nullable=False),
        sa.Column("span_id", UUID(as_uuid=False), nullable=False),
        sa.Column("queue_name", sa.Text, nullable=False),
        sa.Column("depth", sa.Integer, nullable=False),
        sa.Column("env", sa.Text, nullable=False),
        sa.Column("git_sha", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("id", "ts"),
        schema="observability",
    )
    op.create_index(
        "ix_celery_queue_depth_queue_name",
        "celery_queue_depth",
        ["queue_name"],
        schema="observability",
    )
    op.execute(
        "SELECT create_hypertable('observability.celery_queue_depth', 'ts', "
        "chunk_time_interval => INTERVAL '1 hour', if_not_exists => TRUE)"
    )
    op.execute(
        "ALTER TABLE observability.celery_queue_depth SET ("
        "timescaledb.compress, "
        "timescaledb.compress_segmentby = 'queue_name'"
        ")"
    )
    op.execute(
        "SELECT add_compression_policy('observability.celery_queue_depth', "
        "compress_after => INTERVAL '1 day')"
    )

    # ------------------------------------------------------------------
    # ALTER pipeline_runs — add nullable trace_id for correlation
    # ------------------------------------------------------------------
    op.add_column("pipeline_runs", sa.Column("trace_id", UUID(as_uuid=False), nullable=True))


def downgrade() -> None:
    """Drop celery tables and remove trace_id from pipeline_runs."""
    op.drop_column("pipeline_runs", "trace_id")
    op.execute(
        "SELECT remove_compression_policy('observability.celery_queue_depth', if_exists => TRUE)"
    )
    op.execute(
        "SELECT remove_compression_policy("
        "'observability.celery_worker_heartbeat', if_exists => TRUE)"
    )
    op.execute("DROP TABLE IF EXISTS observability.celery_queue_depth CASCADE")
    op.execute("DROP TABLE IF EXISTS observability.beat_schedule_run CASCADE")
    op.execute("DROP TABLE IF EXISTS observability.celery_worker_heartbeat CASCADE")
