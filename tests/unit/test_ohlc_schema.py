"""Unit tests for OHLC price format schemas.

Tests the PriceFormat enum and OHLCResponse Pydantic model used by the
candlestick chart endpoint (GET /stocks/{ticker}/prices?format=ohlc).
"""

from datetime import datetime, timezone

from backend.schemas.stock import OHLCResponse, PriceFormat


class TestPriceFormat:
    """Tests for the PriceFormat enum."""

    def test_list_value(self) -> None:
        """PriceFormat.LIST should have value 'list'."""
        assert PriceFormat.LIST.value == "list"

    def test_ohlc_value(self) -> None:
        """PriceFormat.OHLC should have value 'ohlc'."""
        assert PriceFormat.OHLC.value == "ohlc"

    def test_from_string_list(self) -> None:
        """Should parse 'list' string into PriceFormat.LIST."""
        assert PriceFormat("list") == PriceFormat.LIST

    def test_from_string_ohlc(self) -> None:
        """Should parse 'ohlc' string into PriceFormat.OHLC."""
        assert PriceFormat("ohlc") == PriceFormat.OHLC

    def test_invalid_value_raises(self) -> None:
        """Should raise ValueError for an invalid format string."""
        import pytest

        with pytest.raises(ValueError):
            PriceFormat("candlestick")


class TestOHLCResponse:
    """Tests for the OHLCResponse Pydantic model."""

    def test_construction_with_data(self) -> None:
        """Should construct OHLCResponse with valid parallel arrays."""
        now = datetime.now(timezone.utc)
        resp = OHLCResponse(
            ticker="AAPL",
            period="1mo",
            count=3,
            timestamps=[now, now, now],
            open=[150.0, 151.0, 152.0],
            high=[155.0, 156.0, 157.0],
            low=[149.0, 150.0, 151.0],
            close=[153.0, 154.0, 155.0],
            volume=[1000000, 1100000, 1200000],
        )
        assert resp.ticker == "AAPL"
        assert resp.period == "1mo"
        assert resp.count == 3
        assert len(resp.timestamps) == 3
        assert len(resp.open) == 3
        assert len(resp.close) == 3
        assert len(resp.volume) == 3

    def test_construction_empty(self) -> None:
        """Should construct OHLCResponse with empty arrays and count=0."""
        resp = OHLCResponse(
            ticker="MSFT",
            period="1y",
            count=0,
            timestamps=[],
            open=[],
            high=[],
            low=[],
            close=[],
            volume=[],
        )
        assert resp.count == 0
        assert resp.timestamps == []
        assert resp.open == []

    def test_serialization(self) -> None:
        """Should serialize to dict with all expected keys."""
        now = datetime.now(timezone.utc)
        resp = OHLCResponse(
            ticker="GOOG",
            period="3mo",
            count=1,
            timestamps=[now],
            open=[100.0],
            high=[105.0],
            low=[99.0],
            close=[103.0],
            volume=[500000],
        )
        data = resp.model_dump()
        assert set(data.keys()) == {
            "ticker",
            "period",
            "count",
            "timestamps",
            "open",
            "high",
            "low",
            "close",
            "volume",
        }
