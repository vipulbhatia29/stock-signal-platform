"""Portfolio, Transaction, and Position ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.models.user import User


class Portfolio(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A user's investment portfolio (single account)."""

    __tablename__ = "portfolios"

    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(sa.String(100), nullable=False, default="My Portfolio")
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    # Relationships
    user: Mapped[User] = relationship(back_populates="portfolio")
    transactions: Mapped[list[Transaction]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )
    positions: Mapped[list[Position]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Portfolio id={self.id} user_id={self.user_id} name={self.name!r}>"


class Transaction(UUIDPrimaryKeyMixin, Base):
    """An immutable BUY or SELL trade record (append-only ledger)."""

    __tablename__ = "transactions"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    ticker: Mapped[str] = mapped_column(
        sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"),
        nullable=False,
    )
    transaction_type: Mapped[str] = mapped_column(
        sa.Enum("BUY", "SELL", name="transaction_type_enum"),
        nullable=False,
    )
    shares: Mapped[Decimal] = mapped_column(sa.Numeric(12, 4), nullable=False)
    price_per_share: Mapped[Decimal] = mapped_column(sa.Numeric(12, 4), nullable=False)
    transacted_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        sa.CheckConstraint("shares > 0", name="ck_transactions_shares_positive"),
        sa.CheckConstraint("price_per_share > 0", name="ck_transactions_price_positive"),
    )

    # Relationships
    portfolio: Mapped[Portfolio] = relationship(back_populates="transactions")

    def __repr__(self) -> str:
        return (
            f"<Transaction id={self.id} {self.transaction_type} "
            f"{self.shares} {self.ticker} @ {self.price_per_share}>"
        )


class Position(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Current open position for a ticker — recomputed from transactions via FIFO."""

    __tablename__ = "positions"

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
    opened_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        sa.UniqueConstraint("portfolio_id", "ticker", name="uq_positions_portfolio_ticker"),
    )

    # Relationships
    portfolio: Mapped[Portfolio] = relationship(back_populates="positions")

    def __repr__(self) -> str:
        avg = self.avg_cost_basis
        return f"<Position ticker={self.ticker} shares={self.shares} avg_cost={avg}>"
