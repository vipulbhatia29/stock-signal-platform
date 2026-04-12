"""027_dq_check_history

Revision ID: f1a2b3c4d5e6
Revises: 8c13a01dd3fa
Create Date: 2026-04-12 04:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "8c13a01dd3fa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create dq_check_history table with indexes for DQ finding persistence."""
    op.create_table(
        "dq_check_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("check_name", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("ticker", sa.String(length=10), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_dq_history_detected_at",
        "dq_check_history",
        ["detected_at"],
        unique=False,
        postgresql_using="btree",
    )
    op.create_index(
        "idx_dq_history_check_name",
        "dq_check_history",
        ["check_name", "detected_at"],
        unique=False,
        postgresql_using="btree",
    )


def downgrade() -> None:
    """Drop dq_check_history table and its indexes."""
    op.drop_index("idx_dq_history_check_name", table_name="dq_check_history")
    op.drop_index("idx_dq_history_detected_at", table_name="dq_check_history")
    op.drop_table("dq_check_history")
