"""phase5 forecast pipeline alert models

Revision ID: d68e82e90c96
Revises: ac5d765112d6
Create Date: 2026-03-22 18:56:57.971400

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d68e82e90c96"
down_revision: Union[str, Sequence[str], None] = "ac5d765112d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # --- New tables ---
    op.create_table(
        "pipeline_runs",
        sa.Column("pipeline_name", sa.String(length=50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("tickers_total", sa.Integer(), nullable=False),
        sa.Column("tickers_succeeded", sa.Integer(), nullable=False),
        sa.Column("tickers_failed", sa.Integer(), nullable=False),
        sa.Column(
            "error_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("trigger", sa.String(length=20), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pipeline_runs_pipeline_name"),
        "pipeline_runs",
        ["pipeline_name"],
        unique=False,
    )

    op.create_table(
        "pipeline_watermarks",
        sa.Column("pipeline_name", sa.String(length=50), nullable=False),
        sa.Column("last_completed_date", sa.Date(), nullable=False),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("pipeline_name"),
    )

    op.create_table(
        "in_app_alerts",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("alert_type", sa.String(length=30), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_in_app_alerts_user_id"),
        "in_app_alerts",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "model_versions",
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("model_type", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("training_data_start", sa.Date(), nullable=False),
        sa.Column("training_data_end", sa.Date(), nullable=False),
        sa.Column("data_points", sa.Integer(), nullable=False),
        sa.Column(
            "hyperparameters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("artifact_path", sa.String(length=255), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ticker"], ["stocks.ticker"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_model_versions_ticker"),
        "model_versions",
        ["ticker"],
        unique=False,
    )

    op.create_table(
        "forecast_results",
        sa.Column("forecast_date", sa.Date(), nullable=False),
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("model_version_id", sa.Uuid(), nullable=False),
        sa.Column("predicted_price", sa.Float(), nullable=False),
        sa.Column("predicted_lower", sa.Float(), nullable=False),
        sa.Column("predicted_upper", sa.Float(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("actual_price", sa.Float(), nullable=True),
        sa.Column("error_pct", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ticker"], ["stocks.ticker"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("forecast_date", "ticker", "horizon_days"),
    )

    # TimescaleDB hypertable for forecast_results
    op.execute(
        "SELECT create_hypertable('forecast_results', 'forecast_date', if_not_exists => TRUE);"
    )

    op.create_table(
        "recommendation_outcomes",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("rec_generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rec_ticker", sa.String(length=10), nullable=False),
        sa.Column("action", sa.String(length=10), nullable=False),
        sa.Column("price_at_recommendation", sa.Float(), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual_price", sa.Float(), nullable=False),
        sa.Column("return_pct", sa.Float(), nullable=False),
        sa.Column("spy_return_pct", sa.Float(), nullable=False),
        sa.Column("alpha_pct", sa.Float(), nullable=False),
        sa.Column("action_was_correct", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["rec_generated_at", "rec_ticker"],
            [
                "recommendation_snapshots.generated_at",
                "recommendation_snapshots.ticker",
            ],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- Stock table extension ---
    op.add_column(
        "stocks",
        sa.Column("is_etf", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # NOTE: Intentionally NOT dropping TimescaleDB-managed indexes.
    # Alembic falsely detects them as removed — they are created by
    # create_hypertable() and must not be touched.


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("stocks", "is_etf")
    op.drop_table("recommendation_outcomes")
    op.drop_table("forecast_results")
    op.drop_index(op.f("ix_model_versions_ticker"), table_name="model_versions")
    op.drop_table("model_versions")
    op.drop_index(op.f("ix_in_app_alerts_user_id"), table_name="in_app_alerts")
    op.drop_table("in_app_alerts")
    op.drop_table("pipeline_watermarks")
    op.drop_index(op.f("ix_pipeline_runs_pipeline_name"), table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
