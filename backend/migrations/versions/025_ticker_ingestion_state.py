"""025_ticker_ingestion_state

Revision ID: e1f2a3b4c5d6
Revises: b2351fa2d293
Create Date: 2026-04-06 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "e1f2a3b4c5d6"
down_revision = "b2351fa2d293"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create ticker_ingestion_state table + indexes + backfill from stocks."""
    op.create_table(
        "ticker_ingestion_state",
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("prices_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signals_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fundamentals_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("forecast_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("forecast_retrained_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("news_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sentiment_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("convergence_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("backtest_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recommendation_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["ticker"], ["stocks.ticker"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("ticker"),
    )
    op.create_index(
        "ix_ticker_ingestion_state_prices_updated_at",
        "ticker_ingestion_state",
        ["prices_updated_at"],
    )
    op.create_index(
        "ix_ticker_ingestion_state_signals_updated_at",
        "ticker_ingestion_state",
        ["signals_updated_at"],
    )
    op.create_index(
        "ix_ticker_ingestion_state_forecast_updated_at",
        "ticker_ingestion_state",
        ["forecast_updated_at"],
    )

    # Backfill prices_updated_at from stocks.last_fetched_at. Other columns
    # start NULL and populate organically as tasks run.
    op.execute(
        """
        INSERT INTO ticker_ingestion_state
            (ticker, prices_updated_at, created_at, updated_at)
        SELECT ticker, last_fetched_at, now(), now()
        FROM stocks
        """
    )


def downgrade() -> None:
    """Drop indexes and table (no data to preserve — additive only)."""
    op.drop_index(
        "ix_ticker_ingestion_state_forecast_updated_at",
        table_name="ticker_ingestion_state",
    )
    op.drop_index(
        "ix_ticker_ingestion_state_signals_updated_at",
        table_name="ticker_ingestion_state",
    )
    op.drop_index(
        "ix_ticker_ingestion_state_prices_updated_at",
        table_name="ticker_ingestion_state",
    )
    op.drop_table("ticker_ingestion_state")
