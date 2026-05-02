"""Unit tests for backfill_features script helper functions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest


def _make_price_rows(n: int = 300) -> list:
    """Create mock DB rows for _load_all_prices."""
    dates = pd.bdate_range(end="2025-06-01", periods=n, tz="UTC")
    rng = np.random.default_rng(42)
    prices = 100.0 * np.cumprod(1 + rng.normal(0.0005, 0.015, n))
    highs = prices * 1.01
    lows = prices * 0.99
    volumes = rng.integers(1_000_000, 10_000_000, n).astype(float)
    return [
        (d.to_pydatetime(), float(p), float(h), float(lo), float(v))
        for d, p, h, lo, v in zip(dates, prices, highs, lows, volumes)
    ]


@pytest.mark.asyncio
async def test_load_all_prices_returns_dataframe():
    """_load_all_prices returns DataFrame with DatetimeIndex."""
    from scripts.backfill_features import _load_all_prices

    rows = _make_price_rows(50)
    mock_result = MagicMock()
    mock_result.all.return_value = rows

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    df = await _load_all_prices("AAPL", mock_db)
    assert df is not None
    assert len(df) == 50
    assert "adj_close" in df.columns
    assert "high" in df.columns
    assert "low" in df.columns
    assert "volume" in df.columns
    assert isinstance(df.index, pd.DatetimeIndex)


@pytest.mark.asyncio
async def test_load_all_prices_empty():
    """_load_all_prices returns None when no data."""
    from scripts.backfill_features import _load_all_prices

    mock_result = MagicMock()
    mock_result.all.return_value = []

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await _load_all_prices("ZZZZ", mock_db)
    assert result is None


@pytest.mark.asyncio
async def test_bulk_upsert_empty_df():
    """_bulk_upsert_features returns 0 for empty DataFrame."""
    from scripts.backfill_features import _bulk_upsert_features

    empty_df = pd.DataFrame()
    mock_db = AsyncMock()

    count = await _bulk_upsert_features(empty_df, "AAPL", mock_db)
    assert count == 0
    mock_db.execute.assert_not_called()


def test_download_vix_returns_series():
    """_download_vix_history returns a Series with DatetimeIndex."""
    from scripts.backfill_features import _download_vix_history

    dates = pd.bdate_range(end="2025-06-01", periods=100)
    mock_df = pd.DataFrame(
        {"Close": np.random.default_rng(42).uniform(15, 35, 100)},
        index=dates,
    )

    with patch("scripts.backfill_features.yf.download", return_value=mock_df):
        result = _download_vix_history()
        assert isinstance(result, pd.Series)
        assert len(result) == 100
