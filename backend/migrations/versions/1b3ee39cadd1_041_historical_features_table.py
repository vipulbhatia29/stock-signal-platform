"""041 historical_features table

Revision ID: 1b3ee39cadd1
Revises: e0f1a2b3c4d5
Create Date: 2026-04-28 16:38:44.495226

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1b3ee39cadd1"
down_revision: Union[str, Sequence[str], None] = "e0f1a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create historical_features hypertable for ML training data."""
    op.create_table(
        "historical_features",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("momentum_21d", sa.Float(), nullable=False),
        sa.Column("momentum_63d", sa.Float(), nullable=False),
        sa.Column("momentum_126d", sa.Float(), nullable=False),
        sa.Column("rsi_value", sa.Float(), nullable=False),
        sa.Column("macd_histogram", sa.Float(), nullable=False),
        sa.Column("sma_cross", sa.Integer(), nullable=False),
        sa.Column("bb_position", sa.Integer(), nullable=False),
        sa.Column("volatility", sa.Float(), nullable=False),
        sa.Column("sharpe_ratio", sa.Float(), nullable=False),
        sa.Column("vix_level", sa.Float(), nullable=False),
        sa.Column("spy_momentum_21d", sa.Float(), nullable=False),
        sa.Column("stock_sentiment", sa.Float(), nullable=True),
        sa.Column("sector_sentiment", sa.Float(), nullable=True),
        sa.Column("macro_sentiment", sa.Float(), nullable=True),
        sa.Column("sentiment_confidence", sa.Float(), nullable=True),
        sa.Column("signals_aligned", sa.Integer(), nullable=True),
        sa.Column("convergence_label", sa.String(length=20), nullable=True),
        sa.Column("forward_return_60d", sa.Float(), nullable=True),
        sa.Column("forward_return_90d", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["ticker"], ["stocks.ticker"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("date", "ticker"),
    )
    # Convert to TimescaleDB hypertable
    op.execute(
        "SELECT create_hypertable('historical_features', 'date', "
        "chunk_time_interval => INTERVAL '3 months', "
        "if_not_exists => TRUE)"
    )
    # Index for per-ticker lookups (training queries filter by ticker)
    op.create_index(
        "ix_historical_features_ticker_date",
        "historical_features",
        ["ticker", "date"],
    )


def downgrade() -> None:
    """Drop historical_features hypertable."""
    op.drop_index("ix_historical_features_ticker_date")
    op.drop_table("historical_features")
