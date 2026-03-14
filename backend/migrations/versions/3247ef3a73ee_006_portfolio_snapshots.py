"""006_portfolio_snapshots

Revision ID: 3247ef3a73ee
Revises: 2c45d28eade6
Create Date: 2026-03-14 15:43:39.323174

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3247ef3a73ee"
down_revision: Union[str, Sequence[str], None] = "2c45d28eade6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "portfolio_snapshots",
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_value", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("total_cost_basis", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("unrealized_pnl", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("position_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("portfolio_id", "snapshot_date"),
    )

    # Convert to TimescaleDB hypertable for efficient time-series queries
    op.execute(
        "SELECT create_hypertable('portfolio_snapshots', 'snapshot_date', migrate_data => true)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("portfolio_snapshots")
