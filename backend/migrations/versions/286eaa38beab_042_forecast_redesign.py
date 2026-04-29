"""042 forecast redesign — column renames, new fields, truncate, retire prophet

Revision ID: 286eaa38beab
Revises: 1b3ee39cadd1
Create Date: 2026-04-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "286eaa38beab"
down_revision: Union[str, Sequence[str], None] = "1b3ee39cadd1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply forecast schema redesign.

    Steps (in order):
    1. Rename 4 columns on forecast_results
    2. Add 5 new columns
    3. Truncate old Prophet price predictions
    4. Make base_price NOT NULL after truncate
    5. Remove server defaults (only needed during migration)
    6. Retire all Prophet model_versions
    """
    # ------------------------------------------------------------------ #
    # 1. Rename columns                                                    #
    # ------------------------------------------------------------------ #
    op.alter_column(
        "forecast_results",
        "predicted_price",
        new_column_name="expected_return_pct",
    )
    op.alter_column(
        "forecast_results",
        "predicted_lower",
        new_column_name="return_lower_pct",
    )
    op.alter_column(
        "forecast_results",
        "predicted_upper",
        new_column_name="return_upper_pct",
    )
    op.alter_column(
        "forecast_results",
        "actual_price",
        new_column_name="actual_return_pct",
    )

    # ------------------------------------------------------------------ #
    # 2. Add new columns                                                   #
    # ------------------------------------------------------------------ #
    op.add_column(
        "forecast_results",
        sa.Column(
            "confidence_score",
            sa.Float(),
            nullable=False,
            server_default="0.5",
        ),
    )
    op.add_column(
        "forecast_results",
        sa.Column(
            "direction",
            sa.String(10),
            nullable=False,
            server_default="neutral",
        ),
    )
    op.add_column(
        "forecast_results",
        sa.Column("drivers", JSONB, nullable=True),
    )
    op.add_column(
        "forecast_results",
        sa.Column(
            "base_price",
            sa.Float(),
            nullable=True,  # temporarily nullable until truncate
        ),
    )
    op.add_column(
        "forecast_results",
        sa.Column("forecast_signal", sa.String(30), nullable=True),
    )

    # ------------------------------------------------------------------ #
    # 3. Truncate — old Prophet price predictions are worthless            #
    # ------------------------------------------------------------------ #
    op.execute("TRUNCATE TABLE forecast_results")

    # ------------------------------------------------------------------ #
    # 4. Make base_price NOT NULL after truncate                           #
    # ------------------------------------------------------------------ #
    op.alter_column("forecast_results", "base_price", nullable=False)

    # ------------------------------------------------------------------ #
    # 5. Remove server defaults (not needed for ongoing inserts)           #
    # ------------------------------------------------------------------ #
    op.alter_column(
        "forecast_results",
        "confidence_score",
        server_default=None,
    )
    op.alter_column(
        "forecast_results",
        "direction",
        server_default=None,
    )

    # ------------------------------------------------------------------ #
    # 6. Retire all Prophet model_versions                                 #
    # ------------------------------------------------------------------ #
    op.execute(
        "UPDATE model_versions SET status = 'retired', is_active = false "
        "WHERE model_type = 'prophet'"
    )


def downgrade() -> None:
    """Reverse the forecast schema redesign.

    Note: TRUNCATE and model_versions retirements cannot be reversed — data
    loss is intentional. This downgrade only reverses the schema changes.
    """
    # Drop new columns
    op.drop_column("forecast_results", "forecast_signal")
    op.drop_column("forecast_results", "base_price")
    op.drop_column("forecast_results", "drivers")
    op.drop_column("forecast_results", "direction")
    op.drop_column("forecast_results", "confidence_score")

    # Reverse column renames
    op.alter_column(
        "forecast_results",
        "actual_return_pct",
        new_column_name="actual_price",
    )
    op.alter_column(
        "forecast_results",
        "return_upper_pct",
        new_column_name="predicted_upper",
    )
    op.alter_column(
        "forecast_results",
        "return_lower_pct",
        new_column_name="predicted_lower",
    )
    op.alter_column(
        "forecast_results",
        "expected_return_pct",
        new_column_name="predicted_price",
    )
