"""Dividend payment ORM model — tracks historical dividend distributions."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class DividendPayment(Base):
    """Historical dividend payment record — TimescaleDB hypertable.

    Append-only time-series: one row per ticker per ex-dividend date.
    Fetched from yfinance during data ingestion.
    """

    __tablename__ = "dividend_payments"

    ticker: Mapped[str] = mapped_column(
        sa.ForeignKey("stocks.ticker", ondelete="CASCADE"),
        primary_key=True,
    )
    ex_date: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        primary_key=True,
    )
    amount: Mapped[Decimal] = mapped_column(
        sa.Numeric(10, 4),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<DividendPayment ticker={self.ticker} ex_date={self.ex_date} amount={self.amount}>"
