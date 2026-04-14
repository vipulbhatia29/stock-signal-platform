"""029_backtest_unique_constraint

Revision ID: b3c4d5e6f7a8
Revises: a7b8c9d0e1f2
Create Date: 2026-04-13 20:30:00.000000

Add unique constraint on backtest_runs to prevent duplicate rows on retry.
Constraint: (ticker, model_version_id, config_label, test_start, horizon_days).
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove pre-existing duplicates (keeping most recently created row)
    # before adding the constraint — duplicates from retries are the exact
    # problem this constraint prevents going forward.
    op.execute("""
        DELETE FROM backtest_runs a
        USING backtest_runs b
        WHERE a.created_at < b.created_at
          AND a.ticker = b.ticker
          AND a.model_version_id = b.model_version_id
          AND a.config_label = b.config_label
          AND a.test_start = b.test_start
          AND a.horizon_days = b.horizon_days
    """)
    op.create_unique_constraint(
        "uq_backtest_runs_ticker_mv_config_date_horizon",
        "backtest_runs",
        ["ticker", "model_version_id", "config_label", "test_start", "horizon_days"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_backtest_runs_ticker_mv_config_date_horizon",
        "backtest_runs",
        type_="unique",
    )
