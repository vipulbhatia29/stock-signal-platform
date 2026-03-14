"""API endpoint tests for GET /api/v1/stocks/{ticker}/fundamentals.

Tests cover:
  - Unauthenticated request → 401
  - Valid ticker → 200 with correct fundamentals payload
  - Unknown ticker → 404
  - yfinance partial data (all-None fields) → 200 with null fields (not crash)

fetch_fundamentals is patched to avoid real network calls.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.tools.fundamentals import FundamentalResult
from tests.conftest import StockFactory

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _insert_stock(db_url: str, ticker: str) -> None:
    """Insert a minimal stock record into the test database."""
    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        stock = StockFactory.build(ticker=ticker, is_active=True)
        session.add(stock)
        await session.commit()
    await engine.dispose()


def _make_fundamental_result(ticker: str, **overrides) -> FundamentalResult:
    """Build a FundamentalResult with sensible defaults."""
    defaults = {
        "pe_ratio": 22.5,
        "peg_ratio": 1.4,
        "fcf_yield": 0.04,
        "debt_to_equity": 0.6,
        "piotroski_score": 7,
        "piotroski_breakdown": {
            "positive_roa": 1,
            "positive_cfo": 1,
            "improving_roa": 1,
            "accruals": 1,
            "decreasing_leverage": 1,
            "improving_liquidity": 1,
            "no_dilution": 1,
            "improving_gross_margin": 0,
            "improving_asset_turnover": 0,
        },
    }
    defaults.update(overrides)
    return FundamentalResult(ticker=ticker.upper(), **defaults)


# ─────────────────────────────────────────────────────────────────────────────
# Auth guard
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_fundamentals_unauthenticated(client: AsyncClient):
    """Unauthenticated request must return 401."""
    response = await client.get("/api/v1/stocks/AAPL/fundamentals")
    assert response.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Happy path
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_fundamentals_returns_200(
    auth_client: AsyncClient,
    db_url: str,
):
    """GET /stocks/{ticker}/fundamentals returns 200 with correct payload."""
    await _insert_stock(db_url, "FUND1")
    result = _make_fundamental_result("FUND1")

    with patch("backend.routers.stocks.fetch_fundamentals", return_value=result):
        response = await auth_client.get("/api/v1/stocks/FUND1/fundamentals")

    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "FUND1"
    assert data["pe_ratio"] == pytest.approx(22.5)
    assert data["peg_ratio"] == pytest.approx(1.4)
    assert data["fcf_yield"] == pytest.approx(0.04)
    assert data["debt_to_equity"] == pytest.approx(0.6)
    assert data["piotroski_score"] == 7


@pytest.mark.asyncio
async def test_get_fundamentals_includes_piotroski_breakdown(
    auth_client: AsyncClient,
    db_url: str,
):
    """Response must include piotroski_breakdown with 9 criteria."""
    await _insert_stock(db_url, "FUND2")
    result = _make_fundamental_result("FUND2")

    with patch("backend.routers.stocks.fetch_fundamentals", return_value=result):
        response = await auth_client.get("/api/v1/stocks/FUND2/fundamentals")

    assert response.status_code == 200
    breakdown = response.json()["piotroski_breakdown"]
    assert breakdown["positive_roa"] == 1
    assert breakdown["no_dilution"] == 1
    assert breakdown["improving_gross_margin"] == 0


@pytest.mark.asyncio
async def test_get_fundamentals_null_fields_when_data_missing(
    auth_client: AsyncClient,
    db_url: str,
):
    """When yfinance returns no data, all fields are null — must not crash."""
    await _insert_stock(db_url, "FUND3")
    result = FundamentalResult(
        ticker="FUND3",
        pe_ratio=None,
        peg_ratio=None,
        fcf_yield=None,
        debt_to_equity=None,
        piotroski_score=None,
        piotroski_breakdown={},
    )

    with patch("backend.routers.stocks.fetch_fundamentals", return_value=result):
        response = await auth_client.get("/api/v1/stocks/FUND3/fundamentals")

    assert response.status_code == 200
    data = response.json()
    assert data["pe_ratio"] is None
    assert data["piotroski_score"] is None


# ─────────────────────────────────────────────────────────────────────────────
# Error paths
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_fundamentals_unknown_ticker_returns_404(
    auth_client: AsyncClient,
):
    """Ticker not in the DB must return 404."""
    response = await auth_client.get("/api/v1/stocks/ZZZZ99/fundamentals")
    assert response.status_code == 404
