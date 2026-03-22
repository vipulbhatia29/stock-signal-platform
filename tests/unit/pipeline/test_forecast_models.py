"""Unit tests for Phase 5 database models — forecast, pipeline, and alert."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from backend.models.alert import InAppAlert
from backend.models.forecast import ForecastResult, ModelVersion, RecommendationOutcome
from backend.models.pipeline import PipelineRun, PipelineWatermark

# ---------------------------------------------------------------------------
# ModelVersion
# ---------------------------------------------------------------------------


class TestModelVersion:
    """Tests for the ModelVersion model."""

    def test_create_with_all_fields(self) -> None:
        """ModelVersion should accept all spec-defined fields."""
        mv = ModelVersion(
            id=uuid.uuid4(),
            ticker="AAPL",
            model_type="prophet",
            version=1,
            is_active=True,
            trained_at=datetime.now(timezone.utc),
            training_data_start=date(2024, 1, 1),
            training_data_end=date(2026, 3, 1),
            data_points=500,
            hyperparameters={"changepoint_prior_scale": 0.05},
            metrics={"rolling_mape": 0.08, "mae": 3.2},
            status="active",
            artifact_path="data/models/AAPL_prophet_v1.pkl",
        )
        assert mv.ticker == "AAPL"
        assert mv.model_type == "prophet"
        assert mv.version == 1
        assert mv.is_active is True
        assert mv.data_points == 500
        assert mv.hyperparameters["changepoint_prior_scale"] == 0.05
        assert mv.status == "active"

    def test_repr(self) -> None:
        """ModelVersion __repr__ should include ticker, version, and status."""
        mv = ModelVersion(
            ticker="MSFT",
            version=3,
            status="degraded",
            model_type="prophet",
            trained_at=datetime.now(timezone.utc),
            training_data_start=date(2024, 1, 1),
            training_data_end=date(2026, 1, 1),
            data_points=400,
        )
        assert "MSFT" in repr(mv)
        assert "v3" in repr(mv)
        assert "degraded" in repr(mv)

    def test_default_status_is_active(self) -> None:
        """ModelVersion status should default to 'active'."""
        # Column default is "active" — only applied on flush, so test the column default
        assert ModelVersion.__table__.c.status.default.arg == "active"


# ---------------------------------------------------------------------------
# ForecastResult
# ---------------------------------------------------------------------------


class TestForecastResult:
    """Tests for the ForecastResult model."""

    def test_composite_pk_fields(self) -> None:
        """ForecastResult PK should be (forecast_date, ticker, horizon_days)."""
        pk_cols = [c.name for c in ForecastResult.__table__.primary_key.columns]
        assert pk_cols == ["forecast_date", "ticker", "horizon_days"]

    def test_create_with_all_fields(self) -> None:
        """ForecastResult should accept all spec-defined fields."""
        fr = ForecastResult(
            forecast_date=date(2026, 3, 22),
            ticker="AAPL",
            horizon_days=90,
            model_version_id=uuid.uuid4(),
            predicted_price=195.50,
            predicted_lower=180.00,
            predicted_upper=210.00,
            target_date=date(2026, 6, 20),
            actual_price=None,
            error_pct=None,
            created_at=datetime.now(timezone.utc),
        )
        assert fr.ticker == "AAPL"
        assert fr.horizon_days == 90
        assert fr.predicted_price == 195.50
        assert fr.actual_price is None

    def test_repr(self) -> None:
        """ForecastResult __repr__ should include ticker, date, and horizon."""
        fr = ForecastResult(
            forecast_date=date(2026, 3, 22),
            ticker="TSLA",
            horizon_days=180,
            model_version_id=uuid.uuid4(),
            predicted_price=300.0,
            predicted_lower=250.0,
            predicted_upper=350.0,
            target_date=date(2026, 9, 18),
            created_at=datetime.now(timezone.utc),
        )
        assert "TSLA" in repr(fr)
        assert "180d" in repr(fr)

    def test_model_version_fk_exists(self) -> None:
        """ForecastResult must have a FK to model_versions.id."""
        fks = [fk.target_fullname for fk in ForecastResult.__table__.foreign_keys]
        assert "model_versions.id" in fks


# ---------------------------------------------------------------------------
# RecommendationOutcome
# ---------------------------------------------------------------------------


class TestRecommendationOutcome:
    """Tests for the RecommendationOutcome model."""

    def test_create_buy_correct(self) -> None:
        """RecommendationOutcome for a correct BUY should have positive return."""
        ro = RecommendationOutcome(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            rec_generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            rec_ticker="AAPL",
            action="BUY",
            price_at_recommendation=180.0,
            horizon_days=90,
            evaluated_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            actual_price=200.0,
            return_pct=11.1,
            spy_return_pct=5.0,
            alpha_pct=6.1,
            action_was_correct=True,
            created_at=datetime.now(timezone.utc),
        )
        assert ro.action == "BUY"
        assert ro.action_was_correct is True
        assert ro.alpha_pct == 6.1

    def test_composite_fk_to_recommendation_snapshots(self) -> None:
        """RecommendationOutcome should have composite FK to recommendation_snapshots."""
        fk_targets = set()
        for fk in RecommendationOutcome.__table__.foreign_keys:
            fk_targets.add(fk.target_fullname)
        assert "recommendation_snapshots.generated_at" in fk_targets
        assert "recommendation_snapshots.ticker" in fk_targets

    def test_repr(self) -> None:
        """RecommendationOutcome __repr__ should include ticker, action, horizon."""
        ro = RecommendationOutcome(
            rec_ticker="GOOG",
            action="SELL",
            horizon_days=30,
            action_was_correct=False,
            user_id=uuid.uuid4(),
            rec_generated_at=datetime.now(timezone.utc),
            price_at_recommendation=150.0,
            evaluated_at=datetime.now(timezone.utc),
            actual_price=160.0,
            return_pct=-6.7,
            spy_return_pct=2.0,
            alpha_pct=-8.7,
            created_at=datetime.now(timezone.utc),
        )
        assert "GOOG" in repr(ro)
        assert "SELL" in repr(ro)
        assert "30d" in repr(ro)


# ---------------------------------------------------------------------------
# PipelineWatermark
# ---------------------------------------------------------------------------


class TestPipelineWatermark:
    """Tests for the PipelineWatermark model."""

    def test_create(self) -> None:
        """PipelineWatermark should track pipeline name, date, and status."""
        pw = PipelineWatermark(
            pipeline_name="price_refresh",
            last_completed_date=date(2026, 3, 21),
            last_completed_at=datetime.now(timezone.utc),
            status="ok",
        )
        assert pw.pipeline_name == "price_refresh"
        assert pw.status == "ok"

    def test_status_transitions(self) -> None:
        """PipelineWatermark status should be mutable for state transitions."""
        pw = PipelineWatermark(
            pipeline_name="signal_computation",
            last_completed_date=date(2026, 3, 21),
            last_completed_at=datetime.now(timezone.utc),
            status="ok",
        )
        pw.status = "backfilling"
        assert pw.status == "backfilling"
        pw.status = "failed"
        assert pw.status == "failed"

    def test_pk_is_pipeline_name(self) -> None:
        """PipelineWatermark PK should be pipeline_name (string, not UUID)."""
        pk_cols = [c.name for c in PipelineWatermark.__table__.primary_key.columns]
        assert pk_cols == ["pipeline_name"]

    def test_repr(self) -> None:
        """PipelineWatermark __repr__ should include name, date, and status."""
        pw = PipelineWatermark(
            pipeline_name="forecast_refresh",
            last_completed_date=date(2026, 3, 20),
            last_completed_at=datetime.now(timezone.utc),
            status="ok",
        )
        assert "forecast_refresh" in repr(pw)
        assert "ok" in repr(pw)


# ---------------------------------------------------------------------------
# PipelineRun
# ---------------------------------------------------------------------------


class TestPipelineRun:
    """Tests for the PipelineRun model."""

    def test_create_running(self) -> None:
        """PipelineRun should start in 'running' status."""
        pr = PipelineRun(
            id=uuid.uuid4(),
            pipeline_name="price_refresh",
            started_at=datetime.now(timezone.utc),
            status="running",
            tickers_total=50,
            tickers_succeeded=0,
            tickers_failed=0,
            trigger="scheduled",
        )
        assert pr.status == "running"
        assert pr.completed_at is None

    def test_complete_with_partial_success(self) -> None:
        """PipelineRun can track partial success (some tickers failed)."""
        pr = PipelineRun(
            id=uuid.uuid4(),
            pipeline_name="price_refresh",
            started_at=datetime.now(timezone.utc),
            status="partial",
            tickers_total=50,
            tickers_succeeded=47,
            tickers_failed=3,
            error_summary={"TSLA": "timeout", "GME": "404", "AMC": "rate_limit"},
            completed_at=datetime.now(timezone.utc),
            trigger="scheduled",
        )
        assert pr.tickers_succeeded == 47
        assert pr.tickers_failed == 3
        assert len(pr.error_summary) == 3

    def test_complete_all_success(self) -> None:
        """PipelineRun with all tickers succeeded should have status 'success'."""
        pr = PipelineRun(
            id=uuid.uuid4(),
            pipeline_name="signal_computation",
            started_at=datetime.now(timezone.utc),
            status="success",
            tickers_total=50,
            tickers_succeeded=50,
            tickers_failed=0,
            completed_at=datetime.now(timezone.utc),
            trigger="scheduled",
        )
        assert pr.status == "success"
        assert pr.tickers_failed == 0

    def test_stale_run_detection_fields(self) -> None:
        """PipelineRun with status 'running' and no completed_at is potentially stale."""
        pr = PipelineRun(
            id=uuid.uuid4(),
            pipeline_name="price_refresh",
            started_at=datetime(2026, 3, 22, 1, 0, 0, tzinfo=timezone.utc),
            status="running",
            tickers_total=50,
            trigger="scheduled",
        )
        assert pr.status == "running"
        assert pr.completed_at is None
        # A run is stale if started_at > 1 hour ago and still "running"
        assert pr.started_at < datetime.now(timezone.utc)

    def test_repr(self) -> None:
        """PipelineRun __repr__ should include name, status, and counts."""
        pr = PipelineRun(
            pipeline_name="forecast_refresh",
            status="success",
            tickers_total=10,
            tickers_succeeded=10,
            started_at=datetime.now(timezone.utc),
            trigger="scheduled",
        )
        assert "forecast_refresh" in repr(pr)
        assert "success" in repr(pr)


# ---------------------------------------------------------------------------
# InAppAlert
# ---------------------------------------------------------------------------


class TestInAppAlert:
    """Tests for the InAppAlert model."""

    def test_create_with_metadata(self) -> None:
        """InAppAlert should store alert_type + JSONB metadata for deep-linking."""
        alert = InAppAlert(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            message="AAPL signal changed from SELL to BUY",
            alert_type="signal_change",
            metadata_={"ticker": "AAPL", "route": "/stocks/AAPL"},
            is_read=False,
            created_at=datetime.now(timezone.utc),
        )
        assert alert.alert_type == "signal_change"
        assert alert.metadata_["ticker"] == "AAPL"
        assert alert.is_read is False

    def test_create_without_metadata(self) -> None:
        """InAppAlert should allow null metadata."""
        alert = InAppAlert(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            message="Nightly pipeline completed successfully",
            alert_type="pipeline",
            metadata_=None,
            is_read=False,
            created_at=datetime.now(timezone.utc),
        )
        assert alert.metadata_ is None

    def test_default_is_read_false(self) -> None:
        """InAppAlert is_read column should default to False."""
        assert InAppAlert.__table__.c.is_read.default.arg is False

    def test_repr(self) -> None:
        """InAppAlert __repr__ should include alert_type, user_id, read status."""
        uid = uuid.uuid4()
        alert = InAppAlert(
            user_id=uid,
            alert_type="drift",
            message="test",
            is_read=True,
            created_at=datetime.now(timezone.utc),
        )
        assert "drift" in repr(alert)
        assert str(uid) in repr(alert)
        assert "True" in repr(alert)


# ---------------------------------------------------------------------------
# Stock.is_etf
# ---------------------------------------------------------------------------


class TestStockIsEtf:
    """Tests for the Stock.is_etf column."""

    def test_is_etf_column_exists(self) -> None:
        """Stock model should have an is_etf column."""
        from backend.models.stock import Stock

        assert hasattr(Stock, "is_etf")
        assert "is_etf" in Stock.__table__.c

    def test_is_etf_default_is_false(self) -> None:
        """Stock.is_etf should default to False."""
        from backend.models.stock import Stock

        assert Stock.__table__.c.is_etf.default.arg is False
