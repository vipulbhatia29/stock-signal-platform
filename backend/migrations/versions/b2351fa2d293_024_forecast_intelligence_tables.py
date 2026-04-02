"""024 forecast intelligence tables

Revision ID: b2351fa2d293
Revises: 5c9a05c38ee1
Create Date: 2026-04-02 17:05:01.153736

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b2351fa2d293"
down_revision: Union[str, Sequence[str], None] = "5c9a05c38ee1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create 5 forecast intelligence tables + hypertables + indexes."""
    # 1. backtest_runs — walk-forward backtest results
    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("model_version_id", sa.UUID(), nullable=False),
        sa.Column("config_label", sa.String(length=30), nullable=False),
        sa.Column("train_start", sa.Date(), nullable=False),
        sa.Column("train_end", sa.Date(), nullable=False),
        sa.Column("test_start", sa.Date(), nullable=False),
        sa.Column("test_end", sa.Date(), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("num_windows", sa.Integer(), nullable=False),
        sa.Column("mape", sa.Float(), nullable=False),
        sa.Column("mae", sa.Float(), nullable=False),
        sa.Column("rmse", sa.Float(), nullable=False),
        sa.Column("direction_accuracy", sa.Float(), nullable=False),
        sa.Column("ci_containment", sa.Float(), nullable=False),
        sa.Column("market_regime", sa.String(length=20), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"]),
        sa.ForeignKeyConstraint(["ticker"], ["stocks.ticker"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        "CREATE INDEX ix_backtest_runs_ticker_horizon "
        "ON backtest_runs(ticker, horizon_days, created_at DESC)"
    )

    # 2. signal_convergence_daily — daily convergence snapshot (hypertable)
    op.create_table(
        "signal_convergence_daily",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("rsi_direction", sa.String(length=10), nullable=False),
        sa.Column("macd_direction", sa.String(length=10), nullable=False),
        sa.Column("sma_direction", sa.String(length=10), nullable=False),
        sa.Column("piotroski_direction", sa.String(length=10), nullable=False),
        sa.Column("forecast_direction", sa.String(length=10), nullable=False),
        sa.Column("news_sentiment", sa.Float(), nullable=True),
        sa.Column("signals_aligned", sa.Integer(), nullable=False),
        sa.Column("convergence_label", sa.String(length=20), nullable=False),
        sa.Column("composite_score", sa.Float(), nullable=True),
        sa.Column("actual_return_90d", sa.Float(), nullable=True),
        sa.Column("actual_return_180d", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("date", "ticker"),
    )
    op.execute("SELECT create_hypertable('signal_convergence_daily', 'date', migrate_data => true)")
    op.execute(
        "CREATE INDEX ix_convergence_label "
        "ON signal_convergence_daily(convergence_label, forecast_direction)"
    )

    # 3. news_articles — ingested article metadata (hypertable)
    # PK is (published_at, id) for TimescaleDB compatibility.
    # dedupe_hash unique index must include partitioning column (published_at).
    op.create_table(
        "news_articles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=False),
        sa.Column("ticker", sa.String(length=10), nullable=True),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("event_type", sa.String(length=30), nullable=True),
        sa.Column("dedupe_hash", sa.String(length=64), nullable=False),
        sa.Column("scored_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("published_at", "id"),
    )
    op.execute("SELECT create_hypertable('news_articles', 'published_at', migrate_data => true)")
    # Dedupe index includes partitioning column for TimescaleDB compatibility.
    # App-level dedup uses INSERT ... ON CONFLICT(dedupe_hash, published_at).
    op.execute("CREATE UNIQUE INDEX ix_news_dedupe ON news_articles(dedupe_hash, published_at)")
    op.execute(
        "CREATE INDEX ix_news_articles_ticker_published "
        "ON news_articles(ticker, published_at DESC)"
    )

    # 4. news_sentiment_daily — aggregated daily sentiment (hypertable)
    op.create_table(
        "news_sentiment_daily",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("stock_sentiment", sa.Float(), nullable=False),
        sa.Column("sector_sentiment", sa.Float(), nullable=False),
        sa.Column("macro_sentiment", sa.Float(), nullable=False),
        sa.Column("article_count", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("dominant_event_type", sa.String(length=30), nullable=True),
        sa.Column("rationale_summary", sa.Text(), nullable=True),
        sa.Column("quality_flag", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("date", "ticker"),
    )
    op.execute("SELECT create_hypertable('news_sentiment_daily', 'date', migrate_data => true)")

    # 5. admin_audit_log — admin action trail
    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("target", sa.String(length=100), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("CREATE INDEX ix_audit_user_created ON admin_audit_log(user_id, created_at DESC)")


def downgrade() -> None:
    """Drop all 5 forecast intelligence tables."""
    op.drop_table("admin_audit_log")
    op.drop_table("news_sentiment_daily")
    op.drop_table("news_articles")
    op.drop_table("signal_convergence_daily")
    op.drop_table("backtest_runs")
