"""018 — add severity, title, ticker, dedup_key to in_app_alerts

Revision ID: b8f9d0e1f2a3
Revises: a7b3c4d5e6f7
Create Date: 2026-03-29
"""

import sqlalchemy as sa
from alembic import op

revision: str = "b8f9d0e1f2a3"
down_revision: str = "a7b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "in_app_alerts",
        sa.Column("severity", sa.String(30), server_default="info", nullable=False),
    )
    op.add_column(
        "in_app_alerts",
        sa.Column("title", sa.String(200), server_default="", nullable=False),
    )
    op.add_column(
        "in_app_alerts",
        sa.Column("ticker", sa.String(10), nullable=True),
    )
    op.add_column(
        "in_app_alerts",
        sa.Column("dedup_key", sa.String(100), nullable=True),
    )
    op.create_index(
        "ix_in_app_alerts_dedup",
        "in_app_alerts",
        ["user_id", "dedup_key", "created_at"],
    )
    op.create_index(
        "ix_in_app_alerts_cleanup",
        "in_app_alerts",
        ["is_read", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_in_app_alerts_cleanup", table_name="in_app_alerts")
    op.drop_index("ix_in_app_alerts_dedup", table_name="in_app_alerts")
    op.drop_column("in_app_alerts", "dedup_key")
    op.drop_column("in_app_alerts", "ticker")
    op.drop_column("in_app_alerts", "title")
    op.drop_column("in_app_alerts", "severity")
