"""Pre-1c audit fixes: schema alignment + indexes.

KAN-483: Fix rate_limiter nullable, add request_log_id/parent_span_id/span_id columns.
KAN-484: Add trace_id + ts indexes for 1c query patterns.

Revision ID: c8d9e0f1a2b3
Revises: b7f8c9d0e1a2
Create Date: 2026-04-19
"""

import sqlalchemy as sa
from alembic import op

revision = "c8d9e0f1a2b3"
down_revision = "b7f8c9d0e1a2"
branch_labels = None
depends_on = None

OBS = "observability"


def upgrade() -> None:
    # ── KAN-483: Schema/model alignment fixes ──────────────────────────

    # C2: rate_limiter_event — migration 031 created trace_id/span_id as NOT NULL
    #     but model correctly has nullable=True (fires outside request context).
    op.alter_column(
        "rate_limiter_event",
        "trace_id",
        existing_type=sa.UUID(),
        nullable=True,
        schema=OBS,
    )
    op.alter_column(
        "rate_limiter_event",
        "span_id",
        existing_type=sa.UUID(),
        nullable=True,
        schema=OBS,
    )

    # C4: api_error_log — add request_log_id for linking errors to requests
    op.add_column(
        "api_error_log",
        sa.Column("request_log_id", sa.UUID(), nullable=True),
        schema=OBS,
    )

    # C5: oauth_event_log — add missing span_id for trace correlation
    op.add_column(
        "oauth_event_log",
        sa.Column("span_id", sa.UUID(), nullable=True),
        schema=OBS,
    )

    # H1: Add parent_span_id to 4 tables for trace tree reconstruction
    for table in [
        "api_error_log",
        "slow_query_log",
        "agent_reasoning_log",
        "frontend_error_log",
    ]:
        op.add_column(
            table,
            sa.Column("parent_span_id", sa.UUID(), nullable=True),
            schema=OBS,
        )

    # ── KAN-484: Missing indexes for 1c query patterns ────────────────

    # H2: trace_id indexes (tables that lack them)
    trace_id_tables = [
        ("slow_query_log", "ix_slow_query_log_trace_id"),
        ("cache_operation_log", "ix_cache_operation_log_trace_id"),
        ("celery_worker_heartbeat", "ix_celery_worker_heartbeat_trace_id"),
        ("celery_queue_depth", "ix_celery_queue_depth_trace_id"),
        ("beat_schedule_run", "ix_beat_schedule_run_trace_id"),
        ("db_pool_event", "ix_db_pool_event_trace_id"),
        # auth_event_log trace_id index already created in migration 033
        ("agent_intent_log", "ix_agent_intent_log_trace_id"),
        ("agent_reasoning_log", "ix_agent_reasoning_log_trace_id"),
        ("provider_health_snapshot", "ix_provider_health_snapshot_trace_id"),
        ("rate_limiter_event", "ix_rate_limiter_event_trace_id"),
        ("oauth_event_log", "ix_oauth_event_log_trace_id"),
        ("frontend_error_log", "ix_frontend_error_log_trace_id"),
    ]
    for table, idx_name in trace_id_tables:
        op.create_index(idx_name, table, ["trace_id"], schema=OBS)

    # H4: ts indexes on non-hypertable tables (hypertables use chunk exclusion)
    ts_tables = [
        ("auth_event_log", "ix_auth_event_log_ts"),
        ("beat_schedule_run", "ix_beat_schedule_run_ts"),
        ("db_pool_event", "ix_db_pool_event_ts"),
        ("email_send_log", "ix_email_send_log_ts"),
        ("oauth_event_log", "ix_oauth_event_log_ts"),
        ("agent_intent_log", "ix_agent_intent_log_ts"),
        ("agent_reasoning_log", "ix_agent_reasoning_log_ts"),
        ("frontend_error_log", "ix_frontend_error_log_ts"),
    ]
    for table, idx_name in ts_tables:
        op.create_index(idx_name, table, ["ts"], schema=OBS)

    # M1: api_error_log composite for 5xx filtering (anomaly rule #9)
    op.create_index(
        "ix_api_error_log_status_code_ts",
        "api_error_log",
        ["status_code", "ts"],
        schema=OBS,
    )

    # M2: beat_schedule_run composite for drift anomaly rule (#8)
    op.create_index(
        "ix_beat_schedule_run_drift",
        "beat_schedule_run",
        ["drift_seconds", "ts"],
        schema=OBS,
    )


def downgrade() -> None:
    # Drop composite indexes
    op.drop_index("ix_beat_schedule_run_drift", table_name="beat_schedule_run", schema=OBS)
    op.drop_index("ix_api_error_log_status_code_ts", table_name="api_error_log", schema=OBS)

    # Drop ts indexes
    ts_tables = [
        ("frontend_error_log", "ix_frontend_error_log_ts"),
        ("agent_reasoning_log", "ix_agent_reasoning_log_ts"),
        ("agent_intent_log", "ix_agent_intent_log_ts"),
        ("oauth_event_log", "ix_oauth_event_log_ts"),
        ("email_send_log", "ix_email_send_log_ts"),
        ("db_pool_event", "ix_db_pool_event_ts"),
        ("beat_schedule_run", "ix_beat_schedule_run_ts"),
        ("auth_event_log", "ix_auth_event_log_ts"),
    ]
    for table, idx_name in ts_tables:
        op.drop_index(idx_name, table_name=table, schema=OBS)

    # Drop trace_id indexes
    trace_id_tables = [
        ("frontend_error_log", "ix_frontend_error_log_trace_id"),
        ("oauth_event_log", "ix_oauth_event_log_trace_id"),
        ("rate_limiter_event", "ix_rate_limiter_event_trace_id"),
        ("provider_health_snapshot", "ix_provider_health_snapshot_trace_id"),
        ("agent_reasoning_log", "ix_agent_reasoning_log_trace_id"),
        ("agent_intent_log", "ix_agent_intent_log_trace_id"),
        # auth_event_log trace_id index dropped by migration 033 downgrade
        ("db_pool_event", "ix_db_pool_event_trace_id"),
        ("beat_schedule_run", "ix_beat_schedule_run_trace_id"),
        ("celery_queue_depth", "ix_celery_queue_depth_trace_id"),
        ("celery_worker_heartbeat", "ix_celery_worker_heartbeat_trace_id"),
        ("cache_operation_log", "ix_cache_operation_log_trace_id"),
        ("slow_query_log", "ix_slow_query_log_trace_id"),
    ]
    for table, idx_name in trace_id_tables:
        op.drop_index(idx_name, table_name=table, schema=OBS)

    # Drop added columns
    for table in [
        "frontend_error_log",
        "agent_reasoning_log",
        "slow_query_log",
        "api_error_log",
    ]:
        op.drop_column(table, "parent_span_id", schema=OBS)
    op.drop_column("oauth_event_log", "span_id", schema=OBS)
    op.drop_column("api_error_log", "request_log_id", schema=OBS)

    # Restore NOT NULL on rate_limiter_event
    op.alter_column(
        "rate_limiter_event",
        "span_id",
        existing_type=sa.UUID(),
        nullable=False,
        schema=OBS,
    )
    op.alter_column(
        "rate_limiter_event",
        "trace_id",
        existing_type=sa.UUID(),
        nullable=False,
        schema=OBS,
    )
