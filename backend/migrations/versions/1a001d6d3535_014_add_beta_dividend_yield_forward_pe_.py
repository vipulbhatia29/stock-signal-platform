"""014_add_beta_dividend_yield_forward_pe_to_stocks

Revision ID: 1a001d6d3535
Revises: c965b4058c70
Create Date: 2026-03-25 21:53:55.461022

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1a001d6d3535"
down_revision: Union[str, Sequence[str], None] = "05dd92fc50db"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("stocks", sa.Column("beta", sa.Float(), nullable=True))
    op.add_column("stocks", sa.Column("dividend_yield", sa.Float(), nullable=True))
    op.add_column("stocks", sa.Column("forward_pe", sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("stocks", "forward_pe")
    op.drop_column("stocks", "dividend_yield")
    op.drop_column("stocks", "beta")
