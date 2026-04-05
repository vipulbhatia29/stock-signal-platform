"""Tests for portfolio forecast missing_tickers reporting."""

from backend.schemas.forecasts import PortfolioForecastResponse


def test_missing_tickers_field_exists_with_default():
    """PortfolioForecastResponse has missing_tickers field with empty default."""
    resp = PortfolioForecastResponse(horizons=[], ticker_count=0)
    assert resp.missing_tickers == []


def test_missing_tickers_populated():
    """missing_tickers reports tickers without forecast data."""
    resp = PortfolioForecastResponse(horizons=[], ticker_count=2, missing_tickers=["FORD", "PLTR"])
    assert resp.missing_tickers == ["FORD", "PLTR"]


def test_weight_recomputation_math():
    """Weights sum to 1.0 when some tickers are excluded."""
    # Simulate: AAPL=$4000 (40%), GOOG=$3000 (30%), FORD=$3000 (30%)
    # FORD missing → forecast_value = $7000
    position_values = {"AAPL": 4000.0, "GOOG": 3000.0, "FORD": 3000.0}
    tickers_with_forecast = {"AAPL", "GOOG"}

    forecast_value = sum(v for t, v in position_values.items() if t in tickers_with_forecast)
    assert forecast_value == 7000.0

    weights = {}
    for ticker, value in position_values.items():
        if ticker in tickers_with_forecast:
            weights[ticker] = value / forecast_value

    assert abs(sum(weights.values()) - 1.0) < 1e-10
    assert abs(weights["AAPL"] - 4000 / 7000) < 1e-10
    assert abs(weights["GOOG"] - 3000 / 7000) < 1e-10
    assert "FORD" not in weights


def test_all_tickers_missing():
    """When all tickers missing, response has empty horizons and full missing list."""
    resp = PortfolioForecastResponse(
        horizons=[], ticker_count=0, missing_tickers=["AAPL", "FORD", "GOOG"]
    )
    assert resp.horizons == []
    assert len(resp.missing_tickers) == 3
