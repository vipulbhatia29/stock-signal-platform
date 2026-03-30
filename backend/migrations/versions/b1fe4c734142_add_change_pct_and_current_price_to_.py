"""add change_pct and current_price to signal_snapshots

Revision ID: b1fe4c734142
Revises: d68e82e90c96
Create Date: 2026-03-30 10:56:14.730930

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1fe4c734142"
down_revision: Union[str, Sequence[str], None] = "d68e82e90c96"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add change_pct and current_price columns to signal_snapshots."""
    op.add_column("signal_snapshots", sa.Column("change_pct", sa.Float(), nullable=True))
    op.add_column("signal_snapshots", sa.Column("current_price", sa.Float(), nullable=True))


def downgrade() -> None:
    """Remove change_pct and current_price columns from signal_snapshots."""
    op.drop_column("signal_snapshots", "current_price")
    op.drop_column("signal_snapshots", "change_pct")
