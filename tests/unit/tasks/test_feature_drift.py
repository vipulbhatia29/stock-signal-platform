"""Unit tests for feature distribution drift monitoring.

Tests cover:
  - Clean run (no drift) → status "ok", empty drifted list
  - Drift detected when a feature mean shifts >2σ → status "drift_detected"
  - Disabled via FEATURE_DRIFT_ENABLED=False → status "disabled"
  - Features with std=0 at training time are skipped (no ZeroDivisionError)

All tests mock at the lookup site (evaluation module) per project conventions.
The @tracked_task decorator requires pipeline._db to also be mocked so the
PipelineRunner lifecycle does not attempt real DB writes.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_training_stats(**overrides: dict) -> dict:
    """Build a minimal training feature stats dict."""
    base: dict[str, dict] = {
        "momentum_21d": {"mean": 0.05, "std": 0.02},
        "momentum_63d": {"mean": 0.10, "std": 0.04},
    }
    base.update(overrides)
    return base


def _make_current_stats(**overrides: dict) -> dict:
    """Build a matching current feature stats dict (no drift by default)."""
    base: dict[str, dict] = {
        "momentum_21d": {"mean": 0.051, "std": 0.021},
        "momentum_63d": {"mean": 0.099, "std": 0.039},
    }
    base.update(overrides)
    return base


def _mock_db_context() -> MagicMock:
    """Return a mock _db whose async_session_factory yields a no-op session."""
    mock_session = AsyncMock()
    # scalars().all() returns empty list — no active models to flag
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()

    mock_db = MagicMock()

    @asynccontextmanager
    async def _factory():
        yield mock_session

    mock_db.async_session_factory = _factory
    return mock_db


def _mock_pipeline_db() -> MagicMock:
    """Return a mock _db for the pipeline runner (PipelineRun inserts/updates)."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock())
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()

    mock_db = MagicMock()

    @asynccontextmanager
    async def _factory():
        yield mock_session

    mock_db.async_session_factory = _factory
    return mock_db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_drift_returns_clean() -> None:
    """Current stats that closely match training stats should yield status 'ok'."""
    from backend.tasks.evaluation import _check_feature_drift_async

    # Current means within 1σ of training means → no drift
    training = _make_training_stats()
    current = _make_current_stats()

    mock_settings = MagicMock()
    mock_settings.FEATURE_DRIFT_ENABLED = True
    mock_settings.FEATURE_DRIFT_SIGMA_THRESHOLD = 2.0

    with (
        patch("backend.tasks.evaluation.settings", mock_settings),
        patch(
            "backend.tasks.evaluation._load_training_feature_stats",
            new=AsyncMock(return_value=training),
        ),
        patch(
            "backend.tasks.evaluation._load_current_feature_stats",
            new=AsyncMock(return_value=current),
        ),
        patch("backend.tasks.evaluation._db", _mock_db_context()),
        patch("backend.tasks.pipeline._db", _mock_pipeline_db()),
    ):
        result = await _check_feature_drift_async()

    assert result["status"] == "ok"
    assert result["drifted_features"] == []


@pytest.mark.asyncio
async def test_drift_detected_when_mean_shifts() -> None:
    """A feature whose mean shifts more than 2σ should appear in drifted_features."""
    from backend.tasks.evaluation import _check_feature_drift_async

    # momentum_21d shifts by 3σ → (0.11 - 0.05) / 0.02 = 3.0 > 2.0 threshold
    training = _make_training_stats()
    current = _make_current_stats(momentum_21d={"mean": 0.11, "std": 0.021})

    mock_settings = MagicMock()
    mock_settings.FEATURE_DRIFT_ENABLED = True
    mock_settings.FEATURE_DRIFT_SIGMA_THRESHOLD = 2.0

    with (
        patch("backend.tasks.evaluation.settings", mock_settings),
        patch(
            "backend.tasks.evaluation._load_training_feature_stats",
            new=AsyncMock(return_value=training),
        ),
        patch(
            "backend.tasks.evaluation._load_current_feature_stats",
            new=AsyncMock(return_value=current),
        ),
        patch("backend.tasks.evaluation._db", _mock_db_context()),
        patch("backend.tasks.pipeline._db", _mock_pipeline_db()),
    ):
        result = await _check_feature_drift_async()

    assert result["status"] == "drift_detected"
    assert "momentum_21d" in result["drifted_features"]
    # momentum_63d was not drifted (within threshold)
    assert "momentum_63d" not in result["drifted_features"]


@pytest.mark.asyncio
async def test_disabled_via_config() -> None:
    """When FEATURE_DRIFT_ENABLED=False the check returns status 'disabled' immediately."""
    from backend.tasks.evaluation import _check_feature_drift_async

    mock_settings = MagicMock()
    mock_settings.FEATURE_DRIFT_ENABLED = False

    with (
        patch("backend.tasks.evaluation.settings", mock_settings),
        patch("backend.tasks.pipeline._db", _mock_pipeline_db()),
    ):
        result = await _check_feature_drift_async()

    assert result == {"status": "disabled"}


@pytest.mark.asyncio
async def test_zero_std_skipped() -> None:
    """Features with std=0 in training stats must be skipped (no ZeroDivisionError)."""
    from backend.tasks.evaluation import _check_feature_drift_async

    # momentum_21d has std=0 — any mean shift would cause ZeroDivisionError if not guarded
    training = {
        "momentum_21d": {"mean": 0.05, "std": 0.0},
        "momentum_63d": {"mean": 0.10, "std": 0.04},
    }
    # Give momentum_21d an extreme shift that would flag drift if std check absent
    current = {
        "momentum_21d": {"mean": 999.9, "std": 0.0},
        "momentum_63d": {"mean": 0.10, "std": 0.04},
    }

    mock_settings = MagicMock()
    mock_settings.FEATURE_DRIFT_ENABLED = True
    mock_settings.FEATURE_DRIFT_SIGMA_THRESHOLD = 2.0

    with (
        patch("backend.tasks.evaluation.settings", mock_settings),
        patch(
            "backend.tasks.evaluation._load_training_feature_stats",
            new=AsyncMock(return_value=training),
        ),
        patch(
            "backend.tasks.evaluation._load_current_feature_stats",
            new=AsyncMock(return_value=current),
        ),
        patch("backend.tasks.evaluation._db", _mock_db_context()),
        patch("backend.tasks.pipeline._db", _mock_pipeline_db()),
    ):
        # Must not raise ZeroDivisionError
        result = await _check_feature_drift_async()

    assert result["status"] == "ok"
    assert "momentum_21d" not in result["drifted_features"]
