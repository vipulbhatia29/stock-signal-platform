"""003_index_cleanup

Revision ID: 9e985ae6a70f
Revises: 002_perf_indexes
Create Date: 2026-03-11 12:41:23.467738

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9e985ae6a70f"
down_revision: Union[str, Sequence[str], None] = "002_perf_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add removed_date column to stock_index_memberships
    op.add_column(
        "stock_index_memberships",
        sa.Column("removed_date", sa.DateTime(timezone=True), nullable=True),
    )
    # Add last_synced_at column to stock_indexes
    op.add_column(
        "stock_indexes",
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Drop is_in_universe column from stocks (replaced by index membership)
    op.drop_column("stocks", "is_in_universe")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "stocks",
        sa.Column(
            "is_in_universe",
            sa.BOOLEAN(),
            server_default=sa.text("false"),
            autoincrement=False,
            nullable=False,
        ),
    )
    op.drop_column("stock_indexes", "last_synced_at")
    op.drop_column("stock_index_memberships", "removed_date")
