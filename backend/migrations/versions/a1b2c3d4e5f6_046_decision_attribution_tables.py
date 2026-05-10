"""046_decision_attribution_tables

Revision ID: a1b2c3d4e5f6
Revises: 0ff65ce55dc5
Create Date: 2026-05-10 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "0ff65ce55dc5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # position_snapshots — TimescaleDB hypertable
    op.create_table(
        "position_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("shares", sa.Numeric(12, 4), nullable=False),
        sa.Column("avg_cost_basis", sa.Numeric(12, 4), nullable=False),
        sa.Column("market_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("current_price", sa.Numeric(12, 4), nullable=True),
        sa.Column("asset_type", sa.String(20), nullable=True),
        sa.Column("csv_hash", sa.String(64), nullable=False),
        sa.Column("is_baseline", sa.Boolean(), nullable=False, server_default="false"),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ticker"],
            ["stocks.ticker"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "portfolio_id",
            "ticker",
            "imported_at",
            name="uq_position_snapshots_portfolio_ticker_imported",
        ),
    )
    op.create_index(
        "ix_position_snapshots_portfolio_imported",
        "position_snapshots",
        ["portfolio_id", sa.text("imported_at DESC")],
    )

    # Convert to TimescaleDB hypertable
    op.execute(
        "SELECT create_hypertable('position_snapshots', 'imported_at', "
        "chunk_time_interval => INTERVAL '3 months', migrate_data => true)"
    )

    # position_changes
    op.create_table(
        "position_changes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_before_id", sa.UUID(), nullable=True),
        sa.Column("snapshot_after_id", sa.UUID(), nullable=False),
        sa.Column("prev_shares", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("new_shares", sa.Numeric(12, 4), nullable=False),
        sa.Column("delta_shares", sa.Numeric(12, 4), nullable=False),
        sa.Column("prev_avg_cost_basis", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("new_avg_cost_basis", sa.Numeric(12, 4), nullable=False),
        sa.Column("implied_action", sa.String(10), nullable=False),
        sa.Column("attribution_status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ticker"],
            ["stocks.ticker"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_before_id"],
            ["position_snapshots.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_after_id"],
            ["position_snapshots.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_position_changes_portfolio_detected",
        "position_changes",
        ["portfolio_id", sa.text("detected_at DESC")],
    )
    op.create_index(
        "ix_position_changes_portfolio_ticker",
        "position_changes",
        ["portfolio_id", "ticker"],
    )

    # decision_attributions
    op.create_table(
        "decision_attributions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("position_change_id", sa.UUID(), nullable=False),
        sa.Column("rec_generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rec_ticker", sa.String(20), nullable=False),
        sa.Column("rec_user_id", sa.UUID(), nullable=False),
        sa.Column("rec_action", sa.String(10), nullable=False),
        sa.Column("rec_confidence", sa.String(10), nullable=False),
        sa.Column("match_score", sa.Float(), nullable=False),
        sa.Column("match_reason", sa.Text(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("user_verdict", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["position_change_id"],
            ["position_changes.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_decision_attributions_change_id",
        "decision_attributions",
        ["position_change_id"],
    )
    op.create_index(
        "ix_decision_attributions_primary",
        "decision_attributions",
        ["is_primary"],
        postgresql_where=sa.text("is_primary = true"),
    )


def downgrade() -> None:
    op.drop_table("decision_attributions")
    op.drop_table("position_changes")
    op.drop_table("position_snapshots")
