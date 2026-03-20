"""009 enriched stock data and earnings snapshots

Revision ID: 4bd056089124
Revises: 664e54e974c5
Create Date: 2026-03-20 17:47:09.685230

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4bd056089124"
down_revision: Union[str, Sequence[str], None] = "664e54e974c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add enriched stock columns and earnings_snapshots table."""
    # -- New columns on stocks table (profile, market data, growth, analyst) --
    op.add_column("stocks", sa.Column("business_summary", sa.Text(), nullable=True))
    op.add_column("stocks", sa.Column("employees", sa.Integer(), nullable=True))
    op.add_column("stocks", sa.Column("website", sa.String(length=255), nullable=True))
    op.add_column("stocks", sa.Column("market_cap", sa.Float(), nullable=True))
    op.add_column("stocks", sa.Column("revenue_growth", sa.Float(), nullable=True))
    op.add_column("stocks", sa.Column("gross_margins", sa.Float(), nullable=True))
    op.add_column("stocks", sa.Column("operating_margins", sa.Float(), nullable=True))
    op.add_column("stocks", sa.Column("profit_margins", sa.Float(), nullable=True))
    op.add_column("stocks", sa.Column("return_on_equity", sa.Float(), nullable=True))
    op.add_column("stocks", sa.Column("analyst_target_mean", sa.Float(), nullable=True))
    op.add_column("stocks", sa.Column("analyst_target_high", sa.Float(), nullable=True))
    op.add_column("stocks", sa.Column("analyst_target_low", sa.Float(), nullable=True))
    op.add_column("stocks", sa.Column("analyst_buy", sa.Integer(), nullable=True))
    op.add_column("stocks", sa.Column("analyst_hold", sa.Integer(), nullable=True))
    op.add_column("stocks", sa.Column("analyst_sell", sa.Integer(), nullable=True))

    # -- New earnings_snapshots table --
    op.create_table(
        "earnings_snapshots",
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("quarter", sa.String(length=10), nullable=False),
        sa.Column("eps_estimate", sa.Float(), nullable=True),
        sa.Column("eps_actual", sa.Float(), nullable=True),
        sa.Column("surprise_pct", sa.Float(), nullable=True),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ticker"], ["stocks.ticker"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("ticker", "quarter"),
    )


def downgrade() -> None:
    """Remove enriched stock columns and earnings_snapshots table."""
    op.drop_table("earnings_snapshots")

    op.drop_column("stocks", "analyst_sell")
    op.drop_column("stocks", "analyst_hold")
    op.drop_column("stocks", "analyst_buy")
    op.drop_column("stocks", "analyst_target_low")
    op.drop_column("stocks", "analyst_target_high")
    op.drop_column("stocks", "analyst_target_mean")
    op.drop_column("stocks", "return_on_equity")
    op.drop_column("stocks", "profit_margins")
    op.drop_column("stocks", "operating_margins")
    op.drop_column("stocks", "gross_margins")
    op.drop_column("stocks", "revenue_growth")
    op.drop_column("stocks", "market_cap")
    op.drop_column("stocks", "website")
    op.drop_column("stocks", "employees")
    op.drop_column("stocks", "business_summary")
