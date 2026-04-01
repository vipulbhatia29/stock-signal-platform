"""022 — Add QuantStats columns + rebalancing_suggestions table.

Add per-stock metrics (sortino, max_drawdown, alpha, beta) to signal_snapshots.
Add portfolio metrics (sharpe, sortino, max_drawdown, etc.) to portfolio_snapshots.
Add rebalancing_strategy to user_preferences.
Create rebalancing_suggestions table.
Ensure SPY exists in stocks table.

Revision ID: c870473fe107
Revises: 2146d203aa47
Create Date: 2026-04-01
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "c870473fe107"
down_revision: Union[str, Sequence[str], None] = "2146d203aa47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- signal_snapshots: per-stock QuantStats metrics ---
    op.add_column("signal_snapshots", sa.Column("sortino", sa.Float(), nullable=True))
    op.add_column("signal_snapshots", sa.Column("max_drawdown", sa.Float(), nullable=True))
    op.add_column("signal_snapshots", sa.Column("alpha", sa.Float(), nullable=True))
    op.add_column("signal_snapshots", sa.Column("beta", sa.Float(), nullable=True))
    op.add_column("signal_snapshots", sa.Column("data_days", sa.Integer(), nullable=True))

    # --- portfolio_snapshots: portfolio-level QuantStats metrics ---
    op.add_column("portfolio_snapshots", sa.Column("sharpe", sa.Float(), nullable=True))
    op.add_column("portfolio_snapshots", sa.Column("sortino", sa.Float(), nullable=True))
    op.add_column("portfolio_snapshots", sa.Column("max_drawdown", sa.Float(), nullable=True))
    op.add_column(
        "portfolio_snapshots",
        sa.Column("max_drawdown_duration", sa.Integer(), nullable=True),
    )
    op.add_column("portfolio_snapshots", sa.Column("calmar", sa.Float(), nullable=True))
    op.add_column("portfolio_snapshots", sa.Column("alpha", sa.Float(), nullable=True))
    op.add_column("portfolio_snapshots", sa.Column("beta", sa.Float(), nullable=True))
    op.add_column("portfolio_snapshots", sa.Column("var_95", sa.Float(), nullable=True))
    op.add_column("portfolio_snapshots", sa.Column("cagr", sa.Float(), nullable=True))
    op.add_column("portfolio_snapshots", sa.Column("data_days", sa.Integer(), nullable=True))

    # --- user_preferences: rebalancing strategy ---
    op.add_column(
        "user_preferences",
        sa.Column(
            "rebalancing_strategy",
            sa.String(20),
            nullable=True,
            server_default="min_volatility",
        ),
    )

    # --- rebalancing_suggestions table ---
    op.create_table(
        "rebalancing_suggestions",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("ticker", sa.String(10), nullable=False),
        sa.Column("strategy", sa.String(20), nullable=False),
        sa.Column("target_weight", sa.Float(), nullable=False),
        sa.Column("current_weight", sa.Float(), nullable=False),
        sa.Column("delta_shares", sa.Float(), nullable=False),
        sa.Column("delta_dollars", sa.Float(), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ticker"], ["stocks.ticker"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "portfolio_id",
            "ticker",
            "strategy",
            name="uq_rebal_portfolio_ticker_strategy",
        ),
    )

    # --- Ensure SPY exists for benchmark calculations ---
    op.execute(
        "INSERT INTO stocks (id, ticker, name, is_active) "
        "VALUES (gen_random_uuid(), 'SPY', 'SPDR S&P 500 ETF Trust', true) "
        "ON CONFLICT (ticker) DO NOTHING"
    )


def downgrade() -> None:
    # Drop rebalancing_suggestions table
    op.drop_table("rebalancing_suggestions")

    # Drop user_preferences column
    op.drop_column("user_preferences", "rebalancing_strategy")

    # Drop portfolio_snapshots columns (reverse order)
    portfolio_cols = [
        "data_days",
        "cagr",
        "var_95",
        "beta",
        "alpha",
        "calmar",
        "max_drawdown_duration",
        "max_drawdown",
        "sortino",
        "sharpe",
    ]
    for col in portfolio_cols:
        op.drop_column("portfolio_snapshots", col)

    # Drop signal_snapshots columns (reverse order)
    for col in ["data_days", "beta", "alpha", "max_drawdown", "sortino"]:
        op.drop_column("signal_snapshots", col)
