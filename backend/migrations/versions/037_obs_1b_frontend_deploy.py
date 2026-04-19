"""Obs 1b Frontend + Deploy — frontend_error_log + deploy_events tables.

Revision ID: b7f8c9d0e1a2
Revises: ac67ae322af4
Create Date: 2026-04-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "b7f8c9d0e1a2"
down_revision = "ac67ae322af4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create frontend_error_log and deploy_events tables.

    Both are regular tables (not hypertables) — frontend errors are moderate
    volume with 30d retention; deploy events are very low volume with 365d retention.
    """
    # ------------------------------------------------------------------
    # frontend_error_log (regular table, 30d retention)
    # ------------------------------------------------------------------
    op.create_table(
        "frontend_error_log",
        sa.Column(
            "id",
            UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("trace_id", UUID(as_uuid=False), nullable=True),
        sa.Column("user_id", UUID(as_uuid=False), nullable=True),
        sa.Column("error_type", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_stack", sa.Text(), nullable=True),
        sa.Column("page_route", sa.Text(), nullable=True),
        sa.Column("component_name", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("frontend_metadata", JSONB(), nullable=True),
        sa.Column("env", sa.Text(), nullable=False),
        sa.Column("git_sha", sa.Text(), nullable=True),
        schema="observability",
    )

    op.create_index(
        "ix_frontend_error_log_user_ts",
        "frontend_error_log",
        ["user_id", sa.text("ts DESC")],
        schema="observability",
    )
    op.create_index(
        "ix_frontend_error_log_error_type_ts",
        "frontend_error_log",
        ["error_type", sa.text("ts DESC")],
        schema="observability",
    )
    op.create_index(
        "ix_frontend_error_log_page_route_ts",
        "frontend_error_log",
        ["page_route", sa.text("ts DESC")],
        schema="observability",
    )

    # ------------------------------------------------------------------
    # deploy_events (regular table, 365d retention — low volume, high debug value)
    # ------------------------------------------------------------------
    op.create_table(
        "deploy_events",
        sa.Column(
            "id",
            UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("git_sha", sa.Text(), nullable=False),
        sa.Column("branch", sa.Text(), nullable=False),
        sa.Column("pr_number", sa.Integer(), nullable=True),
        sa.Column("author", sa.Text(), nullable=False),
        sa.Column("commit_message", sa.Text(), nullable=True),
        sa.Column("migrations_applied", JSONB(), nullable=True),
        sa.Column("env", sa.Text(), nullable=False),
        sa.Column("deploy_duration_seconds", sa.Float(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        schema="observability",
    )

    op.create_index(
        "ix_deploy_events_ts",
        "deploy_events",
        [sa.text("ts DESC")],
        schema="observability",
    )
    op.create_index(
        "ix_deploy_events_git_sha",
        "deploy_events",
        ["git_sha"],
        schema="observability",
    )


def downgrade() -> None:
    """Drop frontend_error_log and deploy_events tables."""
    op.drop_table("deploy_events", schema="observability")
    op.drop_table("frontend_error_log", schema="observability")
