"""007_dividend_payments

Revision ID: 821eb511d146
Revises: 3247ef3a73ee
Create Date: 2026-03-14 20:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "821eb511d146"
down_revision: Union[str, Sequence[str], None] = "3247ef3a73ee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create dividend_payments table as a TimescaleDB hypertable."""
    op.create_table(
        "dividend_payments",
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("ex_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.ForeignKeyConstraint(["ticker"], ["stocks.ticker"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("ticker", "ex_date"),
    )

    # Convert to TimescaleDB hypertable for efficient time-series queries
    op.execute(
        "SELECT create_hypertable('dividend_payments', 'ex_date', migrate_data => true)"
    )


def downgrade() -> None:
    """Drop dividend_payments table."""
    op.drop_table("dividend_payments")
