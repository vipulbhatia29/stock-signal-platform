"""Unit tests for HistoricalFeature model."""

from datetime import date

from backend.models.historical_feature import HistoricalFeature


def test_historical_feature_repr():
    """HistoricalFeature repr includes ticker and date."""
    feat = HistoricalFeature(
        date=date(2025, 1, 15),
        ticker="AAPL",
        momentum_21d=0.05,
        momentum_63d=0.12,
        momentum_126d=0.18,
        rsi_value=55.0,
        macd_histogram=0.45,
        sma_cross=2,
        bb_position=1,
        volatility=0.22,
        sharpe_ratio=1.1,
        vix_level=18.5,
        spy_momentum_21d=0.03,
    )
    assert "AAPL" in repr(feat)
    assert "2025-01-15" in repr(feat)


def test_historical_feature_nullable_targets():
    """Forward return targets are nullable (last 90 days won't have them)."""
    feat = HistoricalFeature(
        date=date(2025, 1, 15),
        ticker="AAPL",
        momentum_21d=0.05,
        momentum_63d=0.12,
        momentum_126d=0.18,
        rsi_value=55.0,
        macd_histogram=0.45,
        sma_cross=2,
        bb_position=1,
        volatility=0.22,
        sharpe_ratio=1.1,
        vix_level=18.5,
        spy_momentum_21d=0.03,
    )
    assert feat.forward_return_60d is None
    assert feat.forward_return_90d is None


def test_historical_feature_with_targets():
    """Forward return targets can be set."""
    feat = HistoricalFeature(
        date=date(2025, 1, 15),
        ticker="AAPL",
        momentum_21d=0.05,
        momentum_63d=0.12,
        momentum_126d=0.18,
        rsi_value=55.0,
        macd_histogram=0.45,
        sma_cross=2,
        bb_position=1,
        volatility=0.22,
        sharpe_ratio=1.1,
        vix_level=18.5,
        spy_momentum_21d=0.03,
        forward_return_60d=0.032,
        forward_return_90d=0.048,
    )
    assert feat.forward_return_60d == 0.032
    assert feat.forward_return_90d == 0.048


def test_historical_feature_sentiment_columns_nullable():
    """Sentiment columns exist but default to None (NaN for historical rows)."""
    feat = HistoricalFeature(
        date=date(2025, 1, 15),
        ticker="AAPL",
        momentum_21d=0.05,
        momentum_63d=0.12,
        momentum_126d=0.18,
        rsi_value=55.0,
        macd_histogram=0.45,
        sma_cross=2,
        bb_position=1,
        volatility=0.22,
        sharpe_ratio=1.1,
        vix_level=18.5,
        spy_momentum_21d=0.03,
    )
    assert feat.stock_sentiment is None
    assert feat.sector_sentiment is None
    assert feat.macro_sentiment is None
    assert feat.sentiment_confidence is None


def test_historical_feature_convergence_columns_nullable():
    """Convergence columns exist but default to None (Phase 3 — avoids future migration)."""
    feat = HistoricalFeature(
        date=date(2025, 1, 15),
        ticker="AAPL",
        momentum_21d=0.05,
        momentum_63d=0.12,
        momentum_126d=0.18,
        rsi_value=55.0,
        macd_histogram=0.45,
        sma_cross=2,
        bb_position=1,
        volatility=0.22,
        sharpe_ratio=1.1,
        vix_level=18.5,
        spy_momentum_21d=0.03,
    )
    assert feat.signals_aligned is None
    assert feat.convergence_label is None
