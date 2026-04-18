"""Obs 1b Auth Layer — auth_event_log + oauth_event_log + email_send_log + login_attempts trace_id.

Revision ID: f2a3b4c5d6e7
Revises: 44fdf1e09f76
Create Date: 2026-04-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "f2a3b4c5d6e7"
down_revision = "44fdf1e09f76"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create auth_event_log, oauth_event_log, email_send_log tables and extend login_attempts.

    All three new tables are regular (non-hypertable) tables in the observability schema.
    Low-volume auth events do not benefit from TimescaleDB hypertable partitioning.
    Retention is enforced via row-level DELETE by Celery Beat tasks.

    Also adds nullable trace_id and span_id columns to login_attempts for correlation.
    """
    # ------------------------------------------------------------------
    # auth_event_log
    # ------------------------------------------------------------------
    op.create_table(
        "auth_event_log",
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("trace_id", UUID, nullable=True),
        sa.Column("span_id", UUID, nullable=True),
        sa.Column("user_id", UUID, nullable=True),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("outcome", sa.Text, nullable=False),
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.Column("ip_address", sa.Text, nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("method", sa.Text, nullable=True),
        sa.Column("path", sa.Text, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("env", sa.Text, nullable=False),
        sa.Column("git_sha", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="observability",
    )
    op.create_index(
        "ix_auth_event_log_user_id_ts",
        "auth_event_log",
        ["user_id", sa.text("ts DESC")],
        schema="observability",
    )
    op.create_index(
        "ix_auth_event_log_event_type_outcome_ts",
        "auth_event_log",
        ["event_type", "outcome", sa.text("ts DESC")],
        schema="observability",
    )
    op.create_index(
        "ix_auth_event_log_trace_id",
        "auth_event_log",
        ["trace_id"],
        schema="observability",
        postgresql_where=sa.text("trace_id IS NOT NULL"),
    )

    # ------------------------------------------------------------------
    # oauth_event_log
    # ------------------------------------------------------------------
    op.create_table(
        "oauth_event_log",
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("trace_id", UUID, nullable=True),
        sa.Column("user_id", UUID, nullable=True),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("error_reason", sa.Text, nullable=True),
        sa.Column("attempt_number", sa.Integer, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("env", sa.Text, nullable=False),
        sa.Column("git_sha", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="observability",
    )
    op.create_index(
        "ix_oauth_event_log_user_id_ts",
        "oauth_event_log",
        ["user_id", sa.text("ts DESC")],
        schema="observability",
    )
    op.create_index(
        "ix_oauth_event_log_provider_status_ts",
        "oauth_event_log",
        ["provider", "status", sa.text("ts DESC")],
        schema="observability",
    )

    # ------------------------------------------------------------------
    # email_send_log
    # ------------------------------------------------------------------
    op.create_table(
        "email_send_log",
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("trace_id", UUID, nullable=True),
        sa.Column("user_id", UUID, nullable=True),
        sa.Column("recipient_hash", sa.String(64), nullable=False),
        sa.Column("email_type", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("error_reason", sa.Text, nullable=True),
        sa.Column("resend_message_id", sa.Text, nullable=True),
        sa.Column("env", sa.Text, nullable=False),
        sa.Column("git_sha", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="observability",
    )
    op.create_index(
        "ix_email_send_log_user_id_ts",
        "email_send_log",
        ["user_id", sa.text("ts DESC")],
        schema="observability",
    )
    op.create_index(
        "ix_email_send_log_status_ts",
        "email_send_log",
        ["status", sa.text("ts DESC")],
        schema="observability",
    )

    # ------------------------------------------------------------------
    # login_attempts — additive ALTER TABLE (nullable, no backfill)
    # ------------------------------------------------------------------
    op.add_column("login_attempts", sa.Column("trace_id", UUID, nullable=True))
    op.add_column("login_attempts", sa.Column("span_id", UUID, nullable=True))


def downgrade() -> None:
    """Drop auth_event_log, oauth_event_log, email_send_log; remove login_attempts columns."""
    # Remove added columns from login_attempts
    op.drop_column("login_attempts", "span_id")
    op.drop_column("login_attempts", "trace_id")

    # Drop email_send_log
    op.drop_index(
        "ix_email_send_log_status_ts", table_name="email_send_log", schema="observability"
    )
    op.drop_index(
        "ix_email_send_log_user_id_ts", table_name="email_send_log", schema="observability"
    )
    op.drop_table("email_send_log", schema="observability")

    # Drop oauth_event_log
    op.drop_index(
        "ix_oauth_event_log_provider_status_ts",
        table_name="oauth_event_log",
        schema="observability",
    )
    op.drop_index(
        "ix_oauth_event_log_user_id_ts", table_name="oauth_event_log", schema="observability"
    )
    op.drop_table("oauth_event_log", schema="observability")

    # Drop auth_event_log
    op.drop_index("ix_auth_event_log_trace_id", table_name="auth_event_log", schema="observability")
    op.drop_index(
        "ix_auth_event_log_event_type_outcome_ts",
        table_name="auth_event_log",
        schema="observability",
    )
    op.drop_index(
        "ix_auth_event_log_user_id_ts", table_name="auth_event_log", schema="observability"
    )
    op.drop_table("auth_event_log", schema="observability")
