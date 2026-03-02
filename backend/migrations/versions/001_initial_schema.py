"""Initial schema with TimescaleDB hypertables.

Revision ID: 001_initial
Revises:
Create Date: 2026-03-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all Phase 1 tables and TimescaleDB hypertables."""

    # Enable TimescaleDB extension
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")

    # --- Users ---
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column(
            "role",
            sa.Enum("admin", "user", name="user_role", create_type=True),
            nullable=False,
            server_default="user",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # --- User Preferences ---
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column(
            "timezone", sa.String(50), nullable=False, server_default="America/New_York"
        ),
        sa.Column("default_stop_loss_pct", sa.Float(), nullable=False, server_default="20.0"),
        sa.Column("max_position_pct", sa.Float(), nullable=False, server_default="5.0"),
        sa.Column("max_sector_pct", sa.Float(), nullable=False, server_default="30.0"),
        sa.Column("min_cash_reserve_pct", sa.Float(), nullable=False, server_default="10.0"),
        sa.Column(
            "notify_telegram", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "notify_email", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("quiet_hours_start", sa.Time(), nullable=True),
        sa.Column("quiet_hours_end", sa.Time(), nullable=True),
        sa.Column("composite_weights", JSONB, nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # --- Stocks ---
    op.create_table(
        "stocks",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column("ticker", sa.String(10), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("exchange", sa.String(20), nullable=True),
        sa.Column("sector", sa.String(100), nullable=True),
        sa.Column("industry", sa.String(255), nullable=True),
        sa.Column(
            "is_in_universe", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # --- Watchlist ---
    op.create_table(
        "watchlist",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "ticker",
            sa.String(10),
            sa.ForeignKey("stocks.ticker", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # --- Stock Prices (TimescaleDB hypertable) ---
    op.create_table(
        "stock_prices",
        sa.Column("time", sa.DateTime(timezone=True), primary_key=True),
        sa.Column(
            "ticker",
            sa.String(10),
            sa.ForeignKey("stocks.ticker", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("open", sa.Numeric(12, 4), nullable=False),
        sa.Column("high", sa.Numeric(12, 4), nullable=False),
        sa.Column("low", sa.Numeric(12, 4), nullable=False),
        sa.Column("close", sa.Numeric(12, 4), nullable=False),
        sa.Column("adj_close", sa.Numeric(12, 4), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(50), nullable=False, server_default="yfinance"),
    )
    op.create_index("ix_stock_prices_ticker_time", "stock_prices", ["ticker", sa.text("time DESC")])

    # --- Signal Snapshots (TimescaleDB hypertable) ---
    op.create_table(
        "signal_snapshots",
        sa.Column("computed_at", sa.DateTime(timezone=True), primary_key=True),
        sa.Column(
            "ticker",
            sa.String(10),
            sa.ForeignKey("stocks.ticker", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("rsi_value", sa.Float(), nullable=True),
        sa.Column("rsi_signal", sa.String(20), nullable=True),
        sa.Column("macd_value", sa.Float(), nullable=True),
        sa.Column("macd_histogram", sa.Float(), nullable=True),
        sa.Column("macd_signal_label", sa.String(20), nullable=True),
        sa.Column("sma_50", sa.Float(), nullable=True),
        sa.Column("sma_200", sa.Float(), nullable=True),
        sa.Column("sma_signal", sa.String(20), nullable=True),
        sa.Column("bb_upper", sa.Float(), nullable=True),
        sa.Column("bb_lower", sa.Float(), nullable=True),
        sa.Column("bb_position", sa.String(20), nullable=True),
        sa.Column("annual_return", sa.Float(), nullable=True),
        sa.Column("volatility", sa.Float(), nullable=True),
        sa.Column("sharpe_ratio", sa.Float(), nullable=True),
        sa.Column("composite_score", sa.Float(), nullable=True),
        sa.Column("composite_weights", JSONB, nullable=True),
    )
    op.create_index(
        "ix_signal_snapshots_ticker_computed",
        "signal_snapshots",
        ["ticker", sa.text("computed_at DESC")],
    )

    # --- Recommendation Snapshots (TimescaleDB hypertable) ---
    op.create_table(
        "recommendation_snapshots",
        sa.Column("generated_at", sa.DateTime(timezone=True), primary_key=True),
        sa.Column(
            "ticker",
            sa.String(10),
            sa.ForeignKey("stocks.ticker", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("confidence", sa.String(10), nullable=False),
        sa.Column("composite_score", sa.Float(), nullable=False),
        sa.Column("price_at_recommendation", sa.Numeric(12, 4), nullable=False),
        sa.Column("portfolio_weight_pct", sa.Float(), nullable=True),
        sa.Column("target_weight_pct", sa.Float(), nullable=True),
        sa.Column("suggested_amount_usd", sa.Float(), nullable=True),
        sa.Column("macro_regime", sa.String(20), nullable=True),
        sa.Column("reasoning", JSONB, nullable=True),
        sa.Column(
            "is_actionable", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "acknowledged", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )

    # --- Create TimescaleDB hypertables ---
    op.execute(
        "SELECT create_hypertable('stock_prices', 'time', "
        "chunk_time_interval => INTERVAL '1 month')"
    )
    op.execute(
        "SELECT create_hypertable('signal_snapshots', 'computed_at', "
        "chunk_time_interval => INTERVAL '1 month')"
    )
    op.execute(
        "SELECT create_hypertable('recommendation_snapshots', 'generated_at', "
        "chunk_time_interval => INTERVAL '1 month')"
    )


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table("recommendation_snapshots")
    op.drop_table("signal_snapshots")
    op.drop_table("stock_prices")
    op.drop_table("watchlist")
    op.drop_table("stocks")
    op.drop_table("user_preferences")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS user_role")
