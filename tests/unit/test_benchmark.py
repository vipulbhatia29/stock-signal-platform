"""Tests for benchmark comparison endpoint (KAN-151)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.schemas.stock import BenchmarkComparisonResponse, BenchmarkSeries, PricePeriod

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def mock_stock() -> MagicMock:
    """Mock Stock ORM object."""
    stock = MagicMock()
    stock.ticker = "AAPL"
    stock.name = "Apple Inc."
    return stock


@pytest.fixture
def mock_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    return user


def _make_price_row(ticker: str, time: datetime, close: float) -> MagicMock:
    """Create a mock StockPrice row."""
    row = MagicMock()
    row.ticker = ticker
    row.time = time
    row.close = close
    row.open = close
    row.high = close + 1
    row.low = close - 1
    row.volume = 1000000
    return row


# ── Schema tests ────────────────────────────────────────────────────────────


class TestBenchmarkSchemas:
    def test_series_fields(self, now: datetime) -> None:
        """BenchmarkSeries has required fields."""
        series = BenchmarkSeries(
            ticker="AAPL",
            name="Apple Inc.",
            dates=[now],
            pct_change=[0.0],
        )
        assert series.ticker == "AAPL"
        assert series.pct_change == [0.0]

    def test_response_fields(self, now: datetime) -> None:
        """BenchmarkComparisonResponse wraps series list."""
        resp = BenchmarkComparisonResponse(
            ticker="AAPL",
            period="1y",
            series=[],
        )
        assert resp.ticker == "AAPL"
        assert resp.series == []


# ── Normalization tests ─────────────────────────────────────────────────────


class TestNormalization:
    def test_pct_change_starts_at_zero(self) -> None:
        """First element of pct_change should be 0.0."""
        first_close = 100.0
        closes = [100.0, 110.0, 90.0, 105.0]
        pct = [(c - first_close) / first_close for c in closes]
        assert pct[0] == 0.0
        assert abs(pct[1] - 0.1) < 0.0001
        assert abs(pct[2] - (-0.1)) < 0.0001

    def test_pct_change_calculation(self) -> None:
        """Verify % change math."""
        first_close = 50.0
        closes = [50.0, 75.0, 25.0]
        pct = [(c - first_close) / first_close for c in closes]
        assert pct == [0.0, 0.5, -0.5]


# ── Endpoint tests ──────────────────────────────────────────────────────────


class TestGetBenchmark:
    @pytest.mark.asyncio
    async def test_happy_path_three_series(self, mock_stock: MagicMock, now: datetime) -> None:
        """Happy path returns 3 series (stock + 2 indices)."""
        from backend.routers.stocks.data import get_benchmark

        base = now - timedelta(days=5)
        dates = [base + timedelta(days=i) for i in range(5)]

        # Build price rows for all 3 tickers
        rows = []
        for d in dates:
            rows.append(_make_price_row("AAPL", d, 150.0 + (d - base).days))
            rows.append(_make_price_row("^GSPC", d, 4500.0 + (d - base).days * 10))
            rows.append(_make_price_row("^IXIC", d, 14000.0 + (d - base).days * 30))

        mock_db = AsyncMock()
        # Price query (require_stock is patched, so only price query hits db)
        price_scalars = MagicMock()
        price_scalars.all.return_value = rows
        price_result = MagicMock()
        price_result.scalars.return_value = price_scalars
        mock_db.execute.return_value = price_result

        mock_request = MagicMock()
        mock_request.app.state.cache = None

        with (
            patch("backend.routers.stocks.data.require_stock", return_value=mock_stock),
            patch("backend.routers.stocks.data._ensure_index_fresh", return_value=True),
        ):
            result = await get_benchmark(
                ticker="AAPL",
                request=mock_request,
                period=PricePeriod.ONE_YEAR,
                db=mock_db,
                current_user=MagicMock(),
            )

        assert result.ticker == "AAPL"
        assert result.period == "1y"
        assert len(result.series) == 3
        # First pct_change should be 0.0 for all
        for s in result.series:
            assert s.pct_change[0] == 0.0

    @pytest.mark.asyncio
    async def test_no_price_data_returns_404(self, mock_stock: MagicMock) -> None:
        """No price data for ticker returns 404."""
        from backend.routers.stocks.data import get_benchmark

        mock_db = AsyncMock()
        # Price query returns empty
        price_scalars = MagicMock()
        price_scalars.all.return_value = []
        price_result = MagicMock()
        price_result.scalars.return_value = price_scalars
        mock_db.execute.return_value = price_result

        mock_request = MagicMock()
        mock_request.app.state.cache = None

        with (
            patch("backend.routers.stocks.data.require_stock", return_value=mock_stock),
            patch("backend.routers.stocks.data._ensure_index_fresh", return_value=True),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_benchmark(
                    ticker="AAPL",
                    request=mock_request,
                    period=PricePeriod.ONE_YEAR,
                    db=mock_db,
                    current_user=MagicMock(),
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_graceful_degradation_missing_index(
        self, mock_stock: MagicMock, now: datetime
    ) -> None:
        """If an index is unavailable, returns fewer series."""
        from backend.routers.stocks.data import get_benchmark

        base = now - timedelta(days=3)
        dates = [base + timedelta(days=i) for i in range(3)]
        rows = [_make_price_row("AAPL", d, 150.0) for d in dates]

        mock_db = AsyncMock()
        price_scalars = MagicMock()
        price_scalars.all.return_value = rows
        price_result = MagicMock()
        price_result.scalars.return_value = price_scalars
        mock_db.execute.return_value = price_result

        mock_request = MagicMock()
        mock_request.app.state.cache = None

        with (
            patch("backend.routers.stocks.data.require_stock", return_value=mock_stock),
            patch("backend.routers.stocks.data._ensure_index_fresh", return_value=False),
        ):
            result = await get_benchmark(
                ticker="AAPL",
                request=mock_request,
                period=PricePeriod.ONE_YEAR,
                db=mock_db,
                current_user=MagicMock(),
            )

        # Only stock series (both indices unavailable)
        assert len(result.series) == 1
        assert result.series[0].ticker == "AAPL"

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached(self, mock_stock: MagicMock, now: datetime) -> None:
        """Cache hit returns cached response without DB query."""
        from backend.routers.stocks.data import get_benchmark

        cached_resp = BenchmarkComparisonResponse(
            ticker="AAPL",
            period="1y",
            series=[
                BenchmarkSeries(ticker="AAPL", name="Apple Inc.", dates=[now], pct_change=[0.0])
            ],
        )

        mock_db = AsyncMock()
        mock_cache = AsyncMock()
        mock_cache.get.return_value = cached_resp.model_dump_json()

        mock_request = MagicMock()
        mock_request.app.state.cache = mock_cache

        with patch("backend.routers.stocks.data.require_stock", return_value=mock_stock):
            result = await get_benchmark(
                ticker="AAPL",
                request=mock_request,
                period=PricePeriod.ONE_YEAR,
                db=mock_db,
                current_user=MagicMock(),
            )

        assert result.ticker == "AAPL"
        assert len(result.series) == 1

    @pytest.mark.asyncio
    async def test_date_alignment(self, mock_stock: MagicMock, now: datetime) -> None:
        """Only common dates appear in all series."""
        from backend.routers.stocks.data import get_benchmark

        base = now - timedelta(days=5)
        # Stock has 5 days, index only has 3 (common dates)
        stock_dates = [base + timedelta(days=i) for i in range(5)]
        index_dates = [base + timedelta(days=i) for i in [0, 2, 4]]

        rows = []
        for d in stock_dates:
            rows.append(_make_price_row("AAPL", d, 100.0))
        for d in index_dates:
            rows.append(_make_price_row("^GSPC", d, 4500.0))

        mock_db = AsyncMock()
        price_scalars = MagicMock()
        price_scalars.all.return_value = rows
        price_result = MagicMock()
        price_result.scalars.return_value = price_scalars
        mock_db.execute.return_value = price_result

        mock_request = MagicMock()
        mock_request.app.state.cache = None

        async def mock_ensure(ticker, db):
            return ticker == "^GSPC"

        with (
            patch("backend.routers.stocks.data.require_stock", return_value=mock_stock),
            patch("backend.routers.stocks.data._ensure_index_fresh", side_effect=mock_ensure),
        ):
            result = await get_benchmark(
                ticker="AAPL",
                request=mock_request,
                period=PricePeriod.ONE_YEAR,
                db=mock_db,
                current_user=MagicMock(),
            )

        # Both series should have 3 common dates
        for s in result.series:
            assert len(s.dates) == 3
