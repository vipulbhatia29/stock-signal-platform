"""044 signal scoring gate columns

Revision ID: ebc5d9394dd1
Revises: 757cedd28893
Create Date: 2026-04-30 22:21:19.353102

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ebc5d9394dd1"
down_revision: Union[str, Sequence[str], None] = "757cedd28893"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add 6 new gate indicator columns to signal_snapshots
    op.add_column("signal_snapshots", sa.Column("adx_value", sa.Float(), nullable=True))
    op.add_column("signal_snapshots", sa.Column("obv_slope", sa.Float(), nullable=True))
    op.add_column("signal_snapshots", sa.Column("mfi_value", sa.Float(), nullable=True))
    op.add_column("signal_snapshots", sa.Column("atr_value", sa.Float(), nullable=True))
    op.add_column("signal_snapshots", sa.Column("piotroski_score", sa.Integer(), nullable=True))
    op.add_column("signal_snapshots", sa.Column("macd_histogram_prev", sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("signal_snapshots", "macd_histogram_prev")
    op.drop_column("signal_snapshots", "piotroski_score")
    op.drop_column("signal_snapshots", "atr_value")
    op.drop_column("signal_snapshots", "mfi_value")
    op.drop_column("signal_snapshots", "obv_slope")
    op.drop_column("signal_snapshots", "adx_value")
