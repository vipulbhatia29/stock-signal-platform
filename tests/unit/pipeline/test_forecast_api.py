"""Unit tests for forecast schemas and helper functions."""

from __future__ import annotations

from datetime import date

from backend.routers.forecasts import SECTOR_ETF_MAP, _mape_to_confidence
from backend.schemas.forecasts import (
    ForecastHorizon,
    ForecastResponse,
    HorizonBreakdownResponse,
    PortfolioForecastResponse,
    ScorecardResponse,
    SectorForecastResponse,
)

# ---------------------------------------------------------------------------
# MAPE to confidence helper
# ---------------------------------------------------------------------------


class TestMapeToConfidence:
    """Tests for _mape_to_confidence."""

    def test_high_confidence(self) -> None:
        """MAPE < 10% should be high confidence."""
        assert _mape_to_confidence(0.05) == "high"

    def test_medium_confidence(self) -> None:
        """MAPE 10-20% should be medium confidence."""
        assert _mape_to_confidence(0.15) == "medium"

    def test_low_confidence(self) -> None:
        """MAPE > 20% should be low confidence."""
        assert _mape_to_confidence(0.25) == "low"

    def test_none_defaults_medium(self) -> None:
        """None MAPE should default to medium confidence."""
        assert _mape_to_confidence(None) == "medium"


# ---------------------------------------------------------------------------
# Sector ETF mapping
# ---------------------------------------------------------------------------


class TestSectorEtfMap:
    """Tests for sector to ETF mapping."""

    def test_known_sectors(self) -> None:
        """All 11 sectors should have ETF mappings."""
        assert len(SECTOR_ETF_MAP) == 11
        assert SECTOR_ETF_MAP["technology"] == "XLK"
        assert SECTOR_ETF_MAP["healthcare"] == "XLV"
        assert SECTOR_ETF_MAP["financials"] == "XLF"

    def test_case_insensitive_lookup(self) -> None:
        """Lookup should use lowercase keys."""
        assert "Technology".lower() in SECTOR_ETF_MAP
        assert "ENERGY".lower() in SECTOR_ETF_MAP


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestForecastSchemas:
    """Tests for Pydantic forecast schemas."""

    def test_forecast_horizon_schema(self) -> None:
        """ForecastHorizon should accept all required fields."""
        h = ForecastHorizon(
            horizon_days=90,
            predicted_price=200.0,
            predicted_lower=180.0,
            predicted_upper=220.0,
            target_date=date(2026, 6, 20),
        )
        assert h.horizon_days == 90
        assert h.confidence_level == "medium"
        assert h.sharpe_direction == "flat"

    def test_forecast_response_schema(self) -> None:
        """ForecastResponse should serialize correctly."""
        resp = ForecastResponse(
            ticker="AAPL",
            horizons=[
                ForecastHorizon(
                    horizon_days=90,
                    predicted_price=200.0,
                    predicted_lower=180.0,
                    predicted_upper=220.0,
                    target_date=date(2026, 6, 20),
                )
            ],
            model_mape=0.08,
            model_status="active",
        )
        assert resp.ticker == "AAPL"
        assert len(resp.horizons) == 1

    def test_portfolio_forecast_response(self) -> None:
        """PortfolioForecastResponse should have default empty horizons."""
        resp = PortfolioForecastResponse(horizons=[], ticker_count=0)
        assert resp.ticker_count == 0
        assert resp.vix_regime == "normal"

    def test_sector_forecast_response(self) -> None:
        """SectorForecastResponse should include user tickers."""
        resp = SectorForecastResponse(
            sector="Technology",
            etf_ticker="XLK",
            horizons=[],
            user_tickers_in_sector=["AAPL", "MSFT"],
        )
        assert len(resp.user_tickers_in_sector) == 2

    def test_scorecard_response(self) -> None:
        """ScorecardResponse should accept all scorecard fields."""
        resp = ScorecardResponse(
            total_outcomes=10,
            overall_hit_rate=0.70,
            avg_alpha=0.05,
            buy_hit_rate=0.75,
            sell_hit_rate=0.60,
            worst_miss_pct=-0.25,
            worst_miss_ticker="GME",
            by_horizon=[
                HorizonBreakdownResponse(
                    horizon_days=30,
                    total=5,
                    correct=4,
                    hit_rate=0.80,
                    avg_alpha=0.06,
                ),
            ],
        )
        assert resp.total_outcomes == 10
        assert len(resp.by_horizon) == 1
