"""Add negative_check_count to finding_log for auto-close tracking.

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-04-19
"""

import sqlalchemy as sa
from alembic import op

revision = "e0f1a2b3c4d5"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None

OBS = "observability"


def upgrade() -> None:
    """Add negative_check_count column to finding_log."""
    op.add_column(
        "finding_log",
        sa.Column(
            "negative_check_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        schema=OBS,
    )


def downgrade() -> None:
    """Remove negative_check_count column."""
    op.drop_column("finding_log", "negative_check_count", schema=OBS)
