"""Unit tests for ForecastEngine — LightGBM+XGBoost ensemble."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pandas as pd
import pytest

from backend.services.forecast_engine import (
    FEATURE_LABELS,
    FEATURE_NAMES,
    ForecastEngine,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_synthetic_df(n: int = 100, seed: int = 42) -> pd.DataFrame:
    """Return a synthetic training DataFrame with 17 features + target column.

    Produces ``n`` rows with realistic feature value ranges and a forward
    return column derived from random noise so the LightGBM/XGBoost models
    can be trained without any database interaction.
    """
    rng = np.random.default_rng(seed)
    data: dict[str, object] = {
        "momentum_21d": rng.normal(0.0, 0.05, n),
        "momentum_63d": rng.normal(0.0, 0.08, n),
        "momentum_126d": rng.normal(0.0, 0.12, n),
        "rsi_value": rng.uniform(20, 80, n),
        "macd_histogram": rng.normal(0.0, 1.0, n),
        "sma_cross": rng.integers(0, 3, n).astype(float),
        "bb_position": rng.integers(0, 3, n).astype(float),
        "volatility": rng.uniform(0.01, 0.05, n),
        "sharpe_ratio": rng.normal(0.5, 0.8, n),
        "stock_sentiment": rng.uniform(-1, 1, n),
        "sector_sentiment": rng.uniform(-1, 1, n),
        "macro_sentiment": rng.uniform(-1, 1, n),
        "sentiment_confidence": rng.uniform(0, 1, n),
        "signals_aligned": rng.integers(0, 7, n).astype(float),
        "convergence_label": 0.0,  # numeric — already encoded
        "vix_level": rng.uniform(10, 40, n),
        "spy_momentum_21d": rng.normal(0.0, 0.03, n),
        "forward_return_60d": rng.normal(0.0, 0.08, n),
    }
    return pd.DataFrame(data)


# ---------------------------------------------------------------------------
# Constants / metadata
# ---------------------------------------------------------------------------


def test_feature_labels_covers_all_names() -> None:
    """FEATURE_LABELS must have an entry for every name in FEATURE_NAMES."""
    assert set(FEATURE_LABELS.keys()) == set(FEATURE_NAMES)


# ---------------------------------------------------------------------------
# classify_direction
# ---------------------------------------------------------------------------


def test_classify_direction_bullish() -> None:
    """Returns > 1.0 % → bullish."""
    assert ForecastEngine.classify_direction(3.5) == "bullish"


def test_classify_direction_bearish() -> None:
    """Returns < -1.0 % → bearish."""
    assert ForecastEngine.classify_direction(-2.0) == "bearish"


def test_classify_direction_neutral() -> None:
    """Returns inside [-1.0, 1.0] → neutral."""
    assert ForecastEngine.classify_direction(0.5) == "neutral"


def test_classify_direction_boundary_positive() -> None:
    """Exactly 1.0 % is neutral (exclusive boundary)."""
    assert ForecastEngine.classify_direction(1.0) == "neutral"


def test_classify_direction_boundary_negative() -> None:
    """Exactly -1.0 % is neutral (exclusive boundary)."""
    assert ForecastEngine.classify_direction(-1.0) == "neutral"


# ---------------------------------------------------------------------------
# compute_confidence
# ---------------------------------------------------------------------------


def test_compute_confidence_high() -> None:
    """Tight interval + many signals + low VIX → confidence ≥ 0.70."""
    engine = ForecastEngine()
    score = engine.compute_confidence(interval_width=0.05, signals_aligned=5, vix_regime="low")
    assert score >= 0.70


def test_compute_confidence_low() -> None:
    """Wide interval + few signals + high VIX → confidence < 0.45."""
    engine = ForecastEngine()
    score = engine.compute_confidence(interval_width=0.4, signals_aligned=1, vix_regime="high")
    assert score < 0.45


def test_compute_confidence_clamped_min() -> None:
    """Extreme wide interval must not go below 0.2."""
    engine = ForecastEngine()
    score = engine.compute_confidence(interval_width=10.0, signals_aligned=0, vix_regime="high")
    assert score >= 0.2


def test_compute_confidence_clamped_max() -> None:
    """Perfect inputs must not exceed 0.95."""
    engine = ForecastEngine()
    score = engine.compute_confidence(interval_width=0.0, signals_aligned=6, vix_regime="low")
    assert score <= 0.95


# ---------------------------------------------------------------------------
# confidence_level
# ---------------------------------------------------------------------------


def test_confidence_level_high() -> None:
    """Score ≥ 0.70 → 'high'."""
    assert ForecastEngine.confidence_level(0.75) == "high"


def test_confidence_level_medium() -> None:
    """Score ≥ 0.45 but < 0.70 → 'medium'."""
    assert ForecastEngine.confidence_level(0.55) == "medium"


def test_confidence_level_low() -> None:
    """Score < 0.45 → 'low'."""
    assert ForecastEngine.confidence_level(0.30) == "low"


# ---------------------------------------------------------------------------
# compute_forecast_signal
# ---------------------------------------------------------------------------


def test_forecast_signal_supports_buy() -> None:
    """High conf + bullish + ≥4 aligned → 'supports_buy'."""
    result = ForecastEngine.compute_forecast_signal(
        direction="bullish", confidence=0.80, signals_aligned=5
    )
    assert result == "supports_buy"


def test_forecast_signal_supports_caution() -> None:
    """High conf + bearish + ≥4 aligned → 'supports_caution'."""
    result = ForecastEngine.compute_forecast_signal(
        direction="bearish", confidence=0.75, signals_aligned=4
    )
    assert result == "supports_caution"


def test_forecast_signal_insufficient_low_conf() -> None:
    """Bullish but confidence < 0.70 → 'insufficient_conviction'."""
    result = ForecastEngine.compute_forecast_signal(
        direction="bullish", confidence=0.50, signals_aligned=5
    )
    assert result == "insufficient_conviction"


def test_forecast_signal_insufficient_low_alignment() -> None:
    """Bullish, high conf, but only 2 aligned → 'insufficient_conviction'."""
    result = ForecastEngine.compute_forecast_signal(
        direction="bullish", confidence=0.80, signals_aligned=2
    )
    assert result == "insufficient_conviction"


# ---------------------------------------------------------------------------
# train + predict round-trip (real LightGBM + XGBoost — not mocked)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_train_and_predict_roundtrip() -> None:
    """Train on synthetic data and predict on one row; verify all output keys present."""
    engine = ForecastEngine()
    df = _make_synthetic_df(n=100)

    artifact_bytes, metrics = engine.train(df, horizon_days=60)

    assert isinstance(artifact_bytes, bytes)
    assert len(artifact_bytes) > 0
    assert "direction_accuracy" in metrics
    assert "mean_absolute_error" in metrics
    assert "ci_containment" in metrics

    # Build a single feature dict from the first row
    row = df.iloc[0]
    features = {name: row[name] for name in FEATURE_NAMES}

    result = engine.predict(features, artifact_bytes)

    required_keys = {
        "expected_return_pct",
        "return_lower_pct",
        "return_upper_pct",
        "direction",
        "confidence",
        "confidence_level",
        "drivers",
        "forecast_signal",
    }
    assert required_keys.issubset(result.keys())

    assert isinstance(result["expected_return_pct"], float)
    assert isinstance(result["return_lower_pct"], float)
    assert isinstance(result["return_upper_pct"], float)
    assert result["direction"] in {"bullish", "bearish", "neutral"}
    assert 0.0 <= result["confidence"] <= 1.0
    assert result["confidence_level"] in {"high", "medium", "low"}
    assert result["forecast_signal"] in {
        "supports_buy",
        "supports_caution",
        "insufficient_conviction",
    }


@pytest.mark.slow
def test_explain_top_drivers_returns_list() -> None:
    """After training, explain_top_drivers returns list of well-formed dicts."""
    import io as _io

    import joblib

    engine = ForecastEngine()
    df = _make_synthetic_df(n=100)
    artifact_bytes, _ = engine.train(df, horizon_days=60)

    bundle = joblib.load(_io.BytesIO(artifact_bytes))
    lgb_model = bundle["lgb_q0.5"]

    row = df.iloc[0]
    features = {name: row[name] for name in FEATURE_NAMES}

    drivers = engine.explain_top_drivers(features, lgb_model, top_n=3)

    assert isinstance(drivers, list)
    assert len(drivers) == 3
    for d in drivers:
        assert "feature" in d
        assert "label" in d
        assert "direction" in d
        assert "importance" in d
        assert d["feature"] in FEATURE_NAMES
        assert d["label"] == FEATURE_LABELS[d["feature"]]
        assert d["direction"] in {"bullish", "bearish"}
        assert 0.0 <= d["importance"] <= 1.0


# ---------------------------------------------------------------------------
# assemble_features_bulk — bulk query (no N+1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assemble_features_bulk_single_query() -> None:
    """assemble_features_bulk must issue exactly one DB query for N tickers."""
    engine = ForecastEngine()

    # Build fake HistoricalFeature-like rows for AAPL and MSFT.
    def _make_row(ticker: str) -> MagicMock:
        row = MagicMock()
        row.ticker = ticker
        for name in FEATURE_NAMES:
            setattr(row, name, 0.0)
        return row

    fake_rows = [_make_row("AAPL"), _make_row("MSFT")]

    # Mock the scalars().all() chain.
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = fake_rows

    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=result_mock)

    output = await engine.assemble_features_bulk(["AAPL", "MSFT"], date(2025, 6, 1), mock_db)

    # Exactly one DB round-trip regardless of ticker count.
    mock_db.execute.assert_called_once()

    assert set(output.keys()) == {"AAPL", "MSFT"}
    for ticker_features in output.values():
        assert set(ticker_features.keys()) == set(FEATURE_NAMES)


# ---------------------------------------------------------------------------
# train — edge cases
# ---------------------------------------------------------------------------


def test_train_insufficient_data_raises() -> None:
    """train() must raise ValueError when the DataFrame has fewer than 10 rows."""
    engine = ForecastEngine()
    df = _make_synthetic_df(n=5)
    with pytest.raises(ValueError, match="Insufficient"):
        engine.train(df, horizon_days=60)


def test_train_missing_target_column_raises() -> None:
    """train() must raise ValueError when the target column is absent."""
    engine = ForecastEngine()
    df = _make_synthetic_df(n=100)
    # Remove the expected target column.
    df = df.drop(columns=["forward_return_60d"])
    with pytest.raises(ValueError, match="Target column"):
        engine.train(df, horizon_days=60)
