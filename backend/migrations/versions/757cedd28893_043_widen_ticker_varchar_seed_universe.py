"""043_widen_ticker_varchar_seed_universe

Widen stocks.ticker and model_versions.ticker from VARCHAR(10) to VARCHAR(20)
to accommodate the cross-ticker universe model identifier '__universe__'.
Also seed the '__universe__' synthetic stock record needed by ForecastEngine's
ModelVersion FK.

Revision ID: 757cedd28893
Revises: 286eaa38beab
Create Date: 2026-04-30 03:48:54.800898

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '757cedd28893'
down_revision: Union[str, Sequence[str], None] = '286eaa38beab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Widen ticker columns and seed __universe__ stock record."""
    # Widen VARCHAR(10) → VARCHAR(20) on tables that reference ticker
    op.alter_column("stocks", "ticker", type_=sa.String(20), existing_type=sa.String(10))
    op.alter_column("model_versions", "ticker", type_=sa.String(20), existing_type=sa.String(10))

    # Seed __universe__ synthetic stock for cross-ticker ForecastEngine models
    op.execute(
        "INSERT INTO stocks (id, ticker, name, is_active) "
        "VALUES (gen_random_uuid(), '__universe__', 'Cross-Ticker Universe Model', false) "
        "ON CONFLICT (ticker) DO NOTHING"
    )


def downgrade() -> None:
    """Revert ticker column widths and remove __universe__ record."""
    op.execute("DELETE FROM stocks WHERE ticker = '__universe__'")
    op.alter_column("model_versions", "ticker", type_=sa.String(10), existing_type=sa.String(20))
    op.alter_column("stocks", "ticker", type_=sa.String(10), existing_type=sa.String(20))
