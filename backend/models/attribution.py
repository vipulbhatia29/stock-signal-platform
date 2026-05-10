"""Position snapshot, change tracking, and decision attribution models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PositionSnapshot(Base):
    """Raw position state from a single CSV import.

    One row per ticker per import. TimescaleDB hypertable on imported_at.
    Source of truth for attribution diffs - NOT the Position table.

    Uses composite PK (id, imported_at) because TimescaleDB requires the
    partitioning column in the primary key. A unique constraint on id alone
    supports FK references from position_changes.
    """

    __tablename__ = "position_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    imported_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        primary_key=True,
        default=lambda: datetime.now(timezone.utc),
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    ticker: Mapped[str] = mapped_column(
        sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"),
        nullable=False,
    )
    shares: Mapped[Decimal] = mapped_column(sa.Numeric(12, 4), nullable=False)
    avg_cost_basis: Mapped[Decimal] = mapped_column(sa.Numeric(12, 4), nullable=False)
    market_value: Mapped[Decimal | None] = mapped_column(sa.Numeric(14, 2), nullable=True)
    current_price: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 4), nullable=True)
    asset_type: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    csv_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    is_baseline: Mapped[bool] = mapped_column(sa.Boolean, default=False, nullable=False)

    __table_args__ = (
        sa.UniqueConstraint("id", name="uq_position_snapshots_id"),
        sa.UniqueConstraint(
            "portfolio_id",
            "ticker",
            "imported_at",
            name="uq_position_snapshots_portfolio_ticker_imported",
        ),
        sa.Index(
            "ix_position_snapshots_portfolio_imported",
            "portfolio_id",
            sa.desc("imported_at"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<PositionSnapshot ticker={self.ticker} shares={self.shares} "
            f"imported_at={self.imported_at}>"
        )


class PositionChange(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Detected delta between consecutive CSV snapshots.

    One row per ticker that changed. Drives the attribution matcher.
    """

    __tablename__ = "position_changes"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    ticker: Mapped[str] = mapped_column(
        sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"),
        nullable=False,
    )
    detected_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    snapshot_before_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("position_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )
    snapshot_after_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("position_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    prev_shares: Mapped[Decimal] = mapped_column(
        sa.Numeric(12, 4),
        nullable=False,
        default=0,
    )
    new_shares: Mapped[Decimal] = mapped_column(sa.Numeric(12, 4), nullable=False)
    delta_shares: Mapped[Decimal] = mapped_column(sa.Numeric(12, 4), nullable=False)
    prev_avg_cost_basis: Mapped[Decimal] = mapped_column(
        sa.Numeric(12, 4),
        nullable=False,
        default=0,
    )
    new_avg_cost_basis: Mapped[Decimal] = mapped_column(sa.Numeric(12, 4), nullable=False)
    implied_action: Mapped[str] = mapped_column(sa.String(10), nullable=False)
    attribution_status: Mapped[str] = mapped_column(
        sa.String(10),
        nullable=False,
        default="pending",
    )

    __table_args__ = (
        sa.Index(
            "ix_position_changes_portfolio_detected",
            "portfolio_id",
            sa.desc("detected_at"),
        ),
        sa.Index(
            "ix_position_changes_portfolio_ticker",
            "portfolio_id",
            "ticker",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<PositionChange ticker={self.ticker} {self.implied_action} delta={self.delta_shares}>"
        )


class DecisionAttribution(UUIDPrimaryKeyMixin, Base):
    """Links a position change to a candidate recommendation.

    Multiple candidates per change (scored and ranked). One marked is_primary.
    No hard FK to recommendation_snapshots (hypertable composite PK) -
    key fields are denormalized.
    """

    __tablename__ = "decision_attributions"

    position_change_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("position_changes.id", ondelete="CASCADE"),
        nullable=False,
    )
    rec_generated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
    )
    rec_ticker: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    rec_user_id: Mapped[uuid.UUID] = mapped_column(sa.UUID(), nullable=False)
    rec_action: Mapped[str] = mapped_column(sa.String(10), nullable=False)
    rec_confidence: Mapped[str] = mapped_column(sa.String(10), nullable=False)
    match_score: Mapped[float] = mapped_column(sa.Float, nullable=False)
    match_reason: Mapped[str] = mapped_column(sa.Text, nullable=False)
    is_primary: Mapped[bool] = mapped_column(sa.Boolean, default=False, nullable=False)
    user_verdict: Mapped[str | None] = mapped_column(sa.String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        sa.Index("ix_decision_attributions_change_id", "position_change_id"),
        sa.Index(
            "ix_decision_attributions_primary",
            "is_primary",
            postgresql_where=sa.text("is_primary = true"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<DecisionAttribution change={self.position_change_id} "
            f"rec={self.rec_action} score={self.match_score}>"
        )
