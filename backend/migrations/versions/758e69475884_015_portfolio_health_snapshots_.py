"""015_portfolio_health_snapshots_hypertable

Revision ID: 758e69475884
Revises: 1a001d6d3535
Create Date: 2026-03-25 23:26:52.757342

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "758e69475884"
down_revision: Union[str, Sequence[str], None] = "1a001d6d3535"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create portfolio_health_snapshots table and convert to TimescaleDB hypertable."""
    op.create_table(
        "portfolio_health_snapshots",
        sa.Column(
            "portfolio_id",
            sa.UUID(),
            sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("snapshot_date", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("health_score", sa.Float(), nullable=False),
        sa.Column("grade", sa.String(3), nullable=False),
        sa.Column("diversification_score", sa.Float(), nullable=False),
        sa.Column("signal_quality_score", sa.Float(), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("income_score", sa.Float(), nullable=False),
        sa.Column("sector_balance_score", sa.Float(), nullable=False),
        sa.Column("hhi", sa.Float(), nullable=False),
        sa.Column("weighted_beta", sa.Float(), nullable=True),
        sa.Column("weighted_sharpe", sa.Float(), nullable=True),
        sa.Column("weighted_yield", sa.Float(), nullable=True),
        sa.Column("position_count", sa.Integer(), nullable=False),
    )
    op.execute("SELECT create_hypertable('portfolio_health_snapshots', 'snapshot_date')")


def downgrade() -> None:
    """Drop portfolio_health_snapshots table."""
    op.drop_table("portfolio_health_snapshots")
