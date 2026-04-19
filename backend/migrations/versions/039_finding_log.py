"""Create finding_log table for anomaly engine.

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-04-19
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision = "d9e0f1a2b3c4"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None

OBS = "observability"


def upgrade() -> None:
    """Create finding_log table with indexes."""
    op.create_table(
        "finding_log",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("attribution_layer", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("evidence", JSONB(), nullable=False),
        sa.Column("remediation_hint", sa.Text(), nullable=True),
        sa.Column("related_traces", ARRAY(sa.UUID()), nullable=True),
        sa.Column("acknowledged_by", sa.UUID(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.UUID(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suppressed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suppression_reason", sa.Text(), nullable=True),
        sa.Column("dedup_key", sa.Text(), nullable=False),
        sa.Column("jira_ticket_key", sa.Text(), nullable=True),
        sa.Column("env", sa.Text(), nullable=False),
        schema=OBS,
    )
    op.create_index(
        "ix_finding_log_status_severity_opened",
        "finding_log",
        ["status", "severity", "opened_at"],
        schema=OBS,
    )
    op.create_index(
        "ix_finding_log_dedup_key_status",
        "finding_log",
        ["dedup_key", "status"],
        schema=OBS,
    )
    op.create_index(
        "ix_finding_log_attribution_kind_opened",
        "finding_log",
        ["attribution_layer", "kind", "opened_at"],
        schema=OBS,
    )


def downgrade() -> None:
    """Drop finding_log table and indexes."""
    op.drop_index("ix_finding_log_attribution_kind_opened", table_name="finding_log", schema=OBS)
    op.drop_index("ix_finding_log_dedup_key_status", table_name="finding_log", schema=OBS)
    op.drop_index("ix_finding_log_status_severity_opened", table_name="finding_log", schema=OBS)
    op.drop_table("finding_log", schema=OBS)
