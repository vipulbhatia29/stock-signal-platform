"""Add performance indexes for common query patterns.

Revision ID: 002_perf_indexes
Revises: 311355a05744
Create Date: 2026-03-11

Adds indexes on:
- watchlist.user_id (dashboard watchlist queries)
- recommendation_snapshots.user_id (user recommendations)
- recommendation_snapshots.generated_at (time-range filters)
- signal_snapshots.computed_at (staleness checks, history queries)
- stocks.sector (screener sector filter)
"""

from alembic import op

# revision identifiers
revision = "002_perf_indexes"
down_revision = "311355a05744"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create performance indexes."""
    op.create_index(
        "ix_watchlist_user_id",
        "watchlist",
        ["user_id"],
    )
    op.create_index(
        "ix_recommendation_snapshots_user_id",
        "recommendation_snapshots",
        ["user_id"],
    )
    op.create_index(
        "ix_recommendation_snapshots_generated_at",
        "recommendation_snapshots",
        ["generated_at"],
    )
    op.create_index(
        "ix_signal_snapshots_computed_at",
        "signal_snapshots",
        ["computed_at"],
    )
    op.create_index(
        "ix_stocks_sector",
        "stocks",
        ["sector"],
    )


def downgrade() -> None:
    """Drop performance indexes."""
    op.drop_index("ix_stocks_sector", table_name="stocks")
    op.drop_index(
        "ix_signal_snapshots_computed_at",
        table_name="signal_snapshots",
    )
    op.drop_index(
        "ix_recommendation_snapshots_generated_at",
        table_name="recommendation_snapshots",
    )
    op.drop_index(
        "ix_recommendation_snapshots_user_id",
        table_name="recommendation_snapshots",
    )
    op.drop_index("ix_watchlist_user_id", table_name="watchlist")
