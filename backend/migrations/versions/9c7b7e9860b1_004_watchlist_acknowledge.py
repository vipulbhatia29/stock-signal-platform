"""004_watchlist_acknowledge

Revision ID: 9c7b7e9860b1
Revises: 9e985ae6a70f
Create Date: 2026-03-11 13:41:05.068664

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c7b7e9860b1"
down_revision: Union[str, Sequence[str], None] = "9e985ae6a70f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add price_acknowledged_at to watchlist for stale-data acknowledgement."""
    op.add_column(
        "watchlist",
        sa.Column("price_acknowledged_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Remove price_acknowledged_at from watchlist."""
    op.drop_column("watchlist", "price_acknowledged_at")
