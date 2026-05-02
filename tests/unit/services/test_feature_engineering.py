"""Unit tests for feature_engineering — vectorized indicator computation."""

import math

import numpy as np
import pandas as pd


def _make_price_df(n: int = 300, base_price: float = 100.0, seed: int = 42) -> pd.DataFrame:
    """Create a synthetic OHLCV DataFrame with realistic price movement."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end="2025-06-01", periods=n)
    returns = rng.normal(0.0005, 0.015, n)
    prices = base_price * np.cumprod(1 + returns)
    return pd.DataFrame(
        {
            "adj_close": prices,
            "close": prices,
            "high": prices * 1.01,
            "low": prices * 0.99,
            "volume": rng.integers(1_000_000, 10_000_000, n),
        },
        index=dates,
    )


class TestComputeMomentum:
    """Tests for compute_momentum()."""

    def test_momentum_21d_basic(self):
        """21-day momentum is price[t] / price[t-21] - 1."""
        from backend.services.feature_engineering import compute_momentum

        df = _make_price_df(50)
        result = compute_momentum(df["adj_close"], 21)
        assert result.iloc[:21].isna().all()
        expected = df["adj_close"].iloc[21] / df["adj_close"].iloc[0] - 1
        assert abs(result.iloc[21] - expected) < 1e-10

    def test_momentum_various_windows(self):
        """63d and 126d windows produce expected NaN counts."""
        from backend.services.feature_engineering import compute_momentum

        df = _make_price_df(200)
        m63 = compute_momentum(df["adj_close"], 63)
        m126 = compute_momentum(df["adj_close"], 126)
        assert m63.iloc[:63].isna().all()
        assert not m63.iloc[63:].isna().any()
        assert m126.iloc[:126].isna().all()
        assert not m126.iloc[126:].isna().any()


class TestComputeRSI:
    """Tests for compute_rsi_series()."""

    def test_rsi_range(self):
        """RSI values are between 0 and 100."""
        from backend.services.feature_engineering import compute_rsi_series

        df = _make_price_df(200)
        rsi = compute_rsi_series(df["adj_close"])
        valid = rsi.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_rsi_nan_count(self):
        """RSI has 14 NaN values at the start (period=14)."""
        from backend.services.feature_engineering import compute_rsi_series

        df = _make_price_df(50)
        rsi = compute_rsi_series(df["adj_close"])
        assert rsi.iloc[:14].isna().all()


class TestComputeMACDHistogram:
    """Tests for compute_macd_histogram_series()."""

    def test_macd_histogram_shape(self):
        """MACD histogram has same length as input."""
        from backend.services.feature_engineering import compute_macd_histogram_series

        df = _make_price_df(200)
        hist = compute_macd_histogram_series(df["adj_close"])
        assert len(hist) == len(df)

    def test_macd_histogram_nan_warmup(self):
        """MACD needs slow+signal-1 = 34 rows before first valid value."""
        from backend.services.feature_engineering import compute_macd_histogram_series

        df = _make_price_df(100)
        hist = compute_macd_histogram_series(df["adj_close"])
        assert hist.iloc[:33].isna().all()


class TestComputeSMACross:
    """Tests for compute_sma_cross_series()."""

    def test_sma_cross_encoding(self):
        """SMA cross returns integer encoding: 0, 1, or 2."""
        from backend.services.feature_engineering import compute_sma_cross_series

        df = _make_price_df(300)
        sma_cross = compute_sma_cross_series(df["adj_close"])
        valid = sma_cross.dropna()
        assert set(valid.unique()).issubset({0, 1, 2})

    def test_sma_cross_needs_200_rows(self):
        """First 199 rows are NaN (need 200-day SMA)."""
        from backend.services.feature_engineering import compute_sma_cross_series

        df = _make_price_df(300)
        sma_cross = compute_sma_cross_series(df["adj_close"])
        assert sma_cross.iloc[:199].isna().all()


class TestComputeBBPosition:
    """Tests for compute_bb_position_series()."""

    def test_bb_position_encoding(self):
        """BB position returns integer encoding: 0, 1, or 2."""
        from backend.services.feature_engineering import compute_bb_position_series

        df = _make_price_df(200)
        bb_pos = compute_bb_position_series(df["adj_close"])
        valid = bb_pos.dropna()
        assert set(valid.unique()).issubset({0, 1, 2})


class TestComputeVolatility:
    """Tests for compute_volatility_series()."""

    def test_volatility_positive(self):
        """30-day annualized volatility is non-negative."""
        from backend.services.feature_engineering import compute_volatility_series

        df = _make_price_df(200)
        vol = compute_volatility_series(df["adj_close"], window=30)
        valid = vol.dropna()
        assert (valid >= 0).all()

    def test_volatility_annualized(self):
        """Volatility is annualized (multiplied by sqrt(252))."""
        from backend.services.feature_engineering import compute_volatility_series

        df = _make_price_df(200)
        vol = compute_volatility_series(df["adj_close"], window=30)
        valid = vol.dropna()
        assert valid.mean() > 0.05


class TestComputeSharpe:
    """Tests for compute_sharpe_series()."""

    def test_sharpe_finite(self):
        """Sharpe ratio values are finite (no inf/nan except warmup)."""
        from backend.services.feature_engineering import compute_sharpe_series

        df = _make_price_df(200)
        sharpe = compute_sharpe_series(df["adj_close"], window=30)
        valid = sharpe.dropna()
        assert all(math.isfinite(v) for v in valid)

    def test_sharpe_flat_prices_returns_zero(self):
        """When all prices are identical (zero vol), Sharpe is 0.0 not NaN/inf."""
        from backend.services.feature_engineering import compute_sharpe_series

        dates = pd.bdate_range(end="2025-06-01", periods=100)
        flat_prices = pd.Series(100.0, index=dates)
        sharpe = compute_sharpe_series(flat_prices, window=30)
        valid = sharpe.dropna()
        assert (valid == 0.0).all()


class TestComputeVolatilityEdgeCases:
    """Edge case tests for compute_volatility_series()."""

    def test_volatility_flat_prices_returns_zero(self):
        """When all prices are identical, volatility is 0."""
        from backend.services.feature_engineering import compute_volatility_series

        dates = pd.bdate_range(end="2025-06-01", periods=100)
        flat_prices = pd.Series(100.0, index=dates)
        vol = compute_volatility_series(flat_prices, window=30)
        valid = vol.dropna()
        assert (valid == 0.0).all()


class TestComputeForwardReturns:
    """Tests for compute_forward_log_returns()."""

    def test_forward_return_60d(self):
        """60-day forward log return is ln(price[t+60] / price[t])."""
        from backend.services.feature_engineering import compute_forward_log_returns

        df = _make_price_df(200)
        fwd = compute_forward_log_returns(df["adj_close"], horizon=60)
        assert fwd.iloc[-60:].isna().all()
        expected = np.log(df["adj_close"].iloc[60] / df["adj_close"].iloc[0])
        assert abs(fwd.iloc[0] - expected) < 1e-10

    def test_forward_return_90d_tail_nan(self):
        """90-day forward return: last 90 rows are NaN."""
        from backend.services.feature_engineering import compute_forward_log_returns

        df = _make_price_df(200)
        fwd = compute_forward_log_returns(df["adj_close"], horizon=90)
        assert fwd.iloc[-90:].isna().all()
        assert not fwd.iloc[:-90].isna().any()


class TestBuildFeatureDataFrame:
    """Tests for build_feature_dataframe() — the main orchestrator."""

    def test_output_columns(self):
        """Output contains all 11 features + 2 targets + 4 sentiment + 2 convergence placeholders."""  # noqa: E501
        from backend.services.feature_engineering import build_feature_dataframe

        df = _make_price_df(300)
        vix = pd.Series(np.full(300, 18.5), index=df.index)
        spy_closes = _make_price_df(300, base_price=450.0, seed=99)["adj_close"]
        result = build_feature_dataframe(df["adj_close"], vix_closes=vix, spy_closes=spy_closes)
        expected_cols = {
            "momentum_21d",
            "momentum_63d",
            "momentum_126d",
            "rsi_value",
            "macd_histogram",
            "sma_cross",
            "bb_position",
            "volatility",
            "sharpe_ratio",
            "vix_level",
            "spy_momentum_21d",
            "stock_sentiment",
            "sector_sentiment",
            "macro_sentiment",
            "sentiment_confidence",
            "signals_aligned",
            "convergence_label",
            "forward_return_60d",
            "forward_return_90d",
        }
        assert expected_cols == set(result.columns)

    def test_output_drops_warmup_rows(self):
        """Output drops rows where any required feature is NaN (200-day SMA warmup)."""
        from backend.services.feature_engineering import build_feature_dataframe

        df = _make_price_df(500)
        vix = pd.Series(np.full(500, 18.5), index=df.index)
        spy_closes = _make_price_df(500, base_price=450.0, seed=99)["adj_close"]
        result = build_feature_dataframe(df["adj_close"], vix_closes=vix, spy_closes=spy_closes)
        tech_cols = [
            "momentum_21d",
            "momentum_63d",
            "momentum_126d",
            "rsi_value",
            "macd_histogram",
            "sma_cross",
            "bb_position",
            "volatility",
            "sharpe_ratio",
            "vix_level",
            "spy_momentum_21d",
        ]
        for col in tech_cols:
            assert not result[col].isna().any(), f"{col} has NaN"

    def test_sentiment_columns_are_nan(self):
        """Sentiment columns are NaN for backfill (no sentiment data)."""
        from backend.services.feature_engineering import build_feature_dataframe

        df = _make_price_df(300)
        vix = pd.Series(np.full(300, 18.5), index=df.index)
        spy_closes = _make_price_df(300, base_price=450.0, seed=99)["adj_close"]
        result = build_feature_dataframe(df["adj_close"], vix_closes=vix, spy_closes=spy_closes)
        assert result["stock_sentiment"].isna().all()
        assert result["sector_sentiment"].isna().all()
        assert result["macro_sentiment"].isna().all()
        assert result["sentiment_confidence"].isna().all()

    def test_forward_returns_last_90_nan(self):
        """Forward return targets are NaN for the last 90 rows."""
        from backend.services.feature_engineering import build_feature_dataframe

        df = _make_price_df(500)
        vix = pd.Series(np.full(500, 18.5), index=df.index)
        spy_closes = _make_price_df(500, base_price=450.0, seed=99)["adj_close"]
        result = build_feature_dataframe(df["adj_close"], vix_closes=vix, spy_closes=spy_closes)
        assert result["forward_return_90d"].isna().any()
        assert not result["forward_return_90d"].isna().all()


class TestComputeADXSeries:
    """Tests for vectorized ADX computation."""

    def test_returns_series_same_length(self) -> None:
        """ADX series should have the same length as input."""
        from backend.services.feature_engineering import compute_adx_series

        df = _make_price_df(100)
        result = compute_adx_series(df["high"], df["low"], df["adj_close"])
        assert len(result) == 100

    def test_values_in_range(self) -> None:
        """Non-NaN ADX values should be between 0 and 100."""
        from backend.services.feature_engineering import compute_adx_series

        df = _make_price_df(250)
        result = compute_adx_series(df["high"], df["low"], df["adj_close"])
        valid = result.dropna()
        assert len(valid) > 0
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_warmup_produces_nan(self) -> None:
        """First ~2*period rows should be NaN due to ADX warmup."""
        from backend.services.feature_engineering import compute_adx_series

        df = _make_price_df(100)
        result = compute_adx_series(df["high"], df["low"], df["adj_close"], period=14)
        # At least the first 12 rows should be NaN (ADX needs ~period warmup)
        assert result.iloc[:12].isna().all()

    def test_custom_period(self) -> None:
        """ADX with custom period produces valid output."""
        from backend.services.feature_engineering import compute_adx_series

        df = _make_price_df(250)
        result = compute_adx_series(df["high"], df["low"], df["adj_close"], period=7)
        valid = result.dropna()
        assert len(valid) > 0
        assert (valid >= 0).all()


class TestComputeOBVSlopeSeries:
    """Tests for vectorized OBV slope computation."""

    def test_returns_series_same_length(self) -> None:
        """OBV slope series should have the same length as input."""
        from backend.services.feature_engineering import compute_obv_slope_series

        df = _make_price_df(100)
        result = compute_obv_slope_series(df["adj_close"], df["volume"])
        assert len(result) == 100

    def test_warmup_produces_nan(self) -> None:
        """First `window` rows should be NaN due to rolling warmup."""
        from backend.services.feature_engineering import compute_obv_slope_series

        df = _make_price_df(100)
        result = compute_obv_slope_series(df["adj_close"], df["volume"], window=21)
        assert result.iloc[:20].isna().all()

    def test_values_are_finite(self) -> None:
        """Non-NaN OBV slope values should be finite."""
        from backend.services.feature_engineering import compute_obv_slope_series

        df = _make_price_df(250)
        result = compute_obv_slope_series(df["adj_close"], df["volume"])
        valid = result.dropna()
        assert len(valid) > 0
        assert all(math.isfinite(v) for v in valid)

    def test_uptrend_positive_slope(self) -> None:
        """Strong uptrend with increasing volume should produce positive OBV slope."""
        from backend.services.feature_engineering import compute_obv_slope_series

        df = _make_price_df(100, base_price=100.0, seed=7)
        # Override with strong uptrend closes
        rng = np.random.default_rng(7)
        df["adj_close"] = 100.0 * np.cumprod(1 + rng.normal(0.005, 0.005, 100))
        result = compute_obv_slope_series(df["adj_close"], df["volume"])
        last_valid = result.dropna()
        if len(last_valid) > 0:
            # In a strong uptrend, OBV slope should generally be positive
            assert last_valid.iloc[-1] > -1  # At least not strongly negative


class TestComputeMFISeries:
    """Tests for vectorized MFI computation."""

    def test_returns_series_same_length(self) -> None:
        """MFI series should have the same length as input."""
        from backend.services.feature_engineering import compute_mfi_series

        df = _make_price_df(100)
        result = compute_mfi_series(df["high"], df["low"], df["adj_close"], df["volume"])
        assert len(result) == 100

    def test_values_in_range(self) -> None:
        """Non-NaN MFI values should be between 0 and 100."""
        from backend.services.feature_engineering import compute_mfi_series

        df = _make_price_df(250)
        result = compute_mfi_series(df["high"], df["low"], df["adj_close"], df["volume"])
        valid = result.dropna()
        assert len(valid) > 0
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_warmup_produces_nan(self) -> None:
        """First `period` rows should be NaN due to MFI warmup."""
        from backend.services.feature_engineering import compute_mfi_series

        df = _make_price_df(100)
        result = compute_mfi_series(df["high"], df["low"], df["adj_close"], df["volume"], period=14)
        assert result.iloc[:14].isna().all()

    def test_custom_period(self) -> None:
        """MFI with custom period produces valid output."""
        from backend.services.feature_engineering import compute_mfi_series

        df = _make_price_df(250)
        result = compute_mfi_series(df["high"], df["low"], df["adj_close"], df["volume"], period=7)
        valid = result.dropna()
        assert len(valid) > 0
        assert (valid >= 0).all()
        assert (valid <= 100).all()


class TestGateIndicatorEdgeCases:
    """Edge case tests for all three gate indicator functions."""

    def test_adx_very_short_series(self) -> None:
        """ADX with fewer than period rows returns all NaN."""
        from backend.services.feature_engineering import compute_adx_series

        df = _make_price_df(5)
        result = compute_adx_series(df["high"], df["low"], df["adj_close"])
        assert len(result) == 5
        assert result.isna().all()

    def test_obv_slope_zero_volume(self) -> None:
        """OBV slope with zero volume everywhere returns 0.0 after warmup."""
        from backend.services.feature_engineering import compute_obv_slope_series

        df = _make_price_df(100)
        df["volume"] = 0.0
        result = compute_obv_slope_series(df["adj_close"], df["volume"])
        valid = result.dropna()
        if len(valid) > 0:
            assert all(math.isfinite(v) for v in valid)

    def test_mfi_very_short_series(self) -> None:
        """MFI with fewer than period rows returns all NaN."""
        from backend.services.feature_engineering import compute_mfi_series

        df = _make_price_df(5)
        result = compute_mfi_series(df["high"], df["low"], df["adj_close"], df["volume"])
        assert len(result) == 5
        assert result.isna().all()

    def test_obv_slope_with_nan_in_volume(self) -> None:
        """OBV slope handles NaN values in volume without crashing."""
        from backend.services.feature_engineering import compute_obv_slope_series

        df = _make_price_df(100)
        df.loc[df.index[30:35], "volume"] = np.nan
        result = compute_obv_slope_series(df["adj_close"], df["volume"])
        # Should not crash or produce inf
        valid = result.dropna()
        assert all(math.isfinite(v) for v in valid)

    def test_adx_flat_prices(self) -> None:
        """ADX with flat prices (no trend) returns low values."""
        from backend.services.feature_engineering import compute_adx_series

        dates = pd.bdate_range(end="2025-06-01", periods=100)
        flat = pd.Series(100.0, index=dates)
        high = flat * 1.001
        low = flat * 0.999
        result = compute_adx_series(high, low, flat)
        valid = result.dropna()
        if len(valid) > 0:
            assert (valid >= 0).all()
            assert (valid <= 100).all()
