"""045 historical feature gate columns

Revision ID: 0ff65ce55dc5
Revises: ebc5d9394dd1
Create Date: 2026-05-01 23:51:48.734713

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0ff65ce55dc5"
down_revision: Union[str, Sequence[str], None] = "ebc5d9394dd1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ADX, OBV slope, MFI columns to historical_features for gate scoring."""
    op.add_column("historical_features", sa.Column("adx_value", sa.Float(), nullable=True))
    op.add_column("historical_features", sa.Column("obv_slope", sa.Float(), nullable=True))
    op.add_column("historical_features", sa.Column("mfi_value", sa.Float(), nullable=True))


def downgrade() -> None:
    """Remove gate indicator columns from historical_features."""
    op.drop_column("historical_features", "mfi_value")
    op.drop_column("historical_features", "obv_slope")
    op.drop_column("historical_features", "adx_value")
