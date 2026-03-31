"""Tests for backend.observability.metrics.health_checks."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.observability.metrics.health_checks import (
    _cache,
    get_celery_health,
    get_langfuse_health,
    get_token_budget_status,
)
from backend.observability.token_budget import ModelLimits


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear module-level cache before and after each test."""
    _cache.clear()
    yield
    _cache.clear()


def _mock_session_factory(session: AsyncMock) -> MagicMock:
    """Build a mock async session factory (context manager)."""
    factory = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    factory.return_value = cm
    return factory


# ── Celery health ─────────────────────────────────────────────────────────────


class TestGetCeleryHealth:
    """Tests for get_celery_health."""

    @pytest.mark.asyncio
    async def test_returns_queue_depth(self) -> None:
        """Queue depth is read from Redis llen."""
        redis = AsyncMock()
        redis.llen.return_value = 5

        mock_celery = MagicMock()
        mock_celery.control.inspect.return_value.ping.return_value = {
            "w1": {},
        }
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await get_celery_health(
            redis,
            celery_app=mock_celery,
            session_factory=_mock_session_factory(mock_session),
        )

        assert result["queued"] == 5

    @pytest.mark.asyncio
    async def test_worker_count_from_ping(self) -> None:
        """Worker count comes from inspect().ping() result length."""
        redis = AsyncMock()
        redis.llen.return_value = 0

        mock_celery = MagicMock()
        mock_celery.control.inspect.return_value.ping.return_value = {
            "worker1@host": {"ok": "pong"},
            "worker2@host": {"ok": "pong"},
        }
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await get_celery_health(
            redis,
            celery_app=mock_celery,
            session_factory=_mock_session_factory(mock_session),
        )

        assert result["workers"] == 2

    @pytest.mark.asyncio
    async def test_timeout_returns_workers_none(self) -> None:
        """On timeout, workers is None."""
        redis = AsyncMock()
        redis.llen.return_value = 0

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with patch(
            "backend.observability.metrics.health_checks.asyncio.wait_for",
            side_effect=asyncio.TimeoutError,
        ):
            result = await get_celery_health(
                redis,
                celery_app=MagicMock(),
                session_factory=_mock_session_factory(mock_session),
            )

        assert result["workers"] is None

    @pytest.mark.asyncio
    async def test_cache_prevents_repeated_calls(self) -> None:
        """Second call within TTL returns cached result."""
        redis = AsyncMock()
        redis.llen.return_value = 3

        mock_celery = MagicMock()
        mock_celery.control.inspect.return_value.ping.return_value = {
            "w1": {},
        }
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result1 = await get_celery_health(
            redis,
            celery_app=mock_celery,
            session_factory=_mock_session_factory(mock_session),
        )
        # Reset mock to verify it's not called again
        redis.llen.reset_mock()
        result2 = await get_celery_health(
            redis,
            celery_app=mock_celery,
            session_factory=_mock_session_factory(mock_session),
        )

        assert result1 == result2
        redis.llen.assert_not_called()

    @pytest.mark.asyncio
    async def test_beat_active_from_recent_pipeline_run(self) -> None:
        """Beat is active when last scheduled run is within 26h."""
        redis = AsyncMock()
        redis.llen.return_value = 0

        mock_celery = MagicMock()
        mock_celery.control.inspect.return_value.ping.return_value = None

        mock_session = AsyncMock()
        mock_result = MagicMock()
        recent = datetime.now(timezone.utc) - timedelta(hours=1)
        mock_result.scalar_one_or_none.return_value = recent
        mock_session.execute.return_value = mock_result

        result = await get_celery_health(
            redis,
            celery_app=mock_celery,
            session_factory=_mock_session_factory(mock_session),
        )

        assert result["beat_active"] is True

    @pytest.mark.asyncio
    async def test_beat_inactive_when_no_recent_run(self) -> None:
        """Beat is inactive when last run is older than 26h."""
        redis = AsyncMock()
        redis.llen.return_value = 0

        mock_celery = MagicMock()
        mock_celery.control.inspect.return_value.ping.return_value = None

        mock_session = AsyncMock()
        mock_result = MagicMock()
        stale = datetime.now(timezone.utc) - timedelta(hours=30)
        mock_result.scalar_one_or_none.return_value = stale
        mock_session.execute.return_value = mock_result

        result = await get_celery_health(
            redis,
            celery_app=mock_celery,
            session_factory=_mock_session_factory(mock_session),
        )

        assert result["beat_active"] is False


# ── Langfuse health ───────────────────────────────────────────────────────────


class TestGetLangfuseHealth:
    """Tests for get_langfuse_health."""

    @pytest.mark.asyncio
    async def test_disabled_service_returns_defaults(self) -> None:
        """When service is disabled, return connected=False."""
        service = MagicMock()
        service.enabled = False

        result = await get_langfuse_health(service)

        assert result == {
            "connected": False,
            "traces_today": 0,
            "spans_today": 0,
        }

    @pytest.mark.asyncio
    async def test_auth_check_failure_returns_not_connected(self) -> None:
        """When auth_check raises, connected is False."""
        service = MagicMock()
        service.enabled = True
        service._client.auth_check.side_effect = Exception("refused")

        mock_session = AsyncMock()
        mock_exec = MagicMock()
        mock_exec.scalar_one.return_value = 0
        mock_session.execute.return_value = mock_exec

        result = await get_langfuse_health(
            service,
            session_factory=_mock_session_factory(mock_session),
        )

        assert result["connected"] is False

    @pytest.mark.asyncio
    async def test_auth_check_success(self) -> None:
        """When auth_check succeeds, connected is True."""
        service = MagicMock()
        service.enabled = True
        service._client.auth_check.return_value = True

        mock_session = AsyncMock()
        mock_exec = MagicMock()
        mock_exec.scalar_one.return_value = 42
        mock_session.execute.return_value = mock_exec

        result = await get_langfuse_health(
            service,
            session_factory=_mock_session_factory(mock_session),
        )

        assert result["connected"] is True
        assert result["traces_today"] == 42

    @pytest.mark.asyncio
    async def test_cache_prevents_repeated_calls(self) -> None:
        """Cached result returned within TTL."""
        service = MagicMock()
        service.enabled = False

        result1 = await get_langfuse_health(service)
        # Mutate service to verify cache is used
        service.enabled = True
        result2 = await get_langfuse_health(service)

        assert result1 == result2
        assert result2["connected"] is False


# ── TokenBudget status ────────────────────────────────────────────────────────


class TestGetTokenBudgetStatus:
    """Tests for get_token_budget_status."""

    @pytest.mark.asyncio
    async def test_none_returns_empty(self) -> None:
        """None token_budget returns empty list."""
        result = await get_token_budget_status(None)
        assert result == []

    @pytest.mark.asyncio
    async def test_no_limits_returns_empty(self) -> None:
        """TokenBudget with empty limits returns empty list."""
        budget = MagicMock()
        budget._limits = {}
        budget._redis = AsyncMock()

        result = await get_token_budget_status(budget)
        assert result == []

    @pytest.mark.asyncio
    async def test_no_redis_returns_empty(self) -> None:
        """TokenBudget without Redis returns empty list."""
        budget = MagicMock()
        budget._limits = {
            "gpt-4": ModelLimits(tpm=100000, rpm=30, tpd=1000000, rpd=1000),
        }
        budget._redis = None

        result = await get_token_budget_status(budget)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_usage_percentages(self) -> None:
        """Computes correct TPM/RPM usage percentages."""
        redis = AsyncMock()
        budget = MagicMock()
        budget._limits = {
            "gpt-4": ModelLimits(tpm=100000, rpm=100, tpd=1000000, rpd=1000),
        }
        budget._redis = redis
        budget._ensure_prune_script = AsyncMock(return_value="sha")

        # TPM: 50000/100000 = 50%, RPM: 25/100 = 25%
        redis.evalsha.side_effect = [50000, 25]

        result = await get_token_budget_status(budget)

        assert len(result) == 1
        assert result[0]["model"] == "gpt-4"
        assert result[0]["tpm_used_pct"] == 50.0
        assert result[0]["rpm_used_pct"] == 25.0

    @pytest.mark.asyncio
    async def test_multiple_models(self) -> None:
        """Returns status for all configured models."""
        redis = AsyncMock()
        budget = MagicMock()
        budget._limits = {
            "gpt-4": ModelLimits(tpm=100000, rpm=100, tpd=1000000, rpd=1000),
            "groq-llama": ModelLimits(tpm=50000, rpm=30, tpd=500000, rpd=500),
        }
        budget._redis = redis
        budget._ensure_prune_script = AsyncMock(return_value="sha")

        # gpt-4: tpm=10000, rpm=10; groq: tpm=25000, rpm=15
        redis.evalsha.side_effect = [10000, 10, 25000, 15]

        result = await get_token_budget_status(budget)

        assert len(result) == 2
        models = {r["model"]: r for r in result}
        assert models["gpt-4"]["tpm_used_pct"] == 10.0
        assert models["gpt-4"]["rpm_used_pct"] == 10.0
        assert models["groq-llama"]["tpm_used_pct"] == 50.0
        assert models["groq-llama"]["rpm_used_pct"] == 50.0

    @pytest.mark.asyncio
    async def test_redis_error_returns_zero_pct(self) -> None:
        """If Redis fails for a model, that model gets 0% usage."""
        redis = AsyncMock()
        budget = MagicMock()
        budget._limits = {
            "gpt-4": ModelLimits(tpm=100000, rpm=100, tpd=1000000, rpd=1000),
        }
        budget._redis = redis
        budget._ensure_prune_script = AsyncMock(return_value="sha")
        redis.evalsha.side_effect = Exception("NOSCRIPT")

        result = await get_token_budget_status(budget)

        assert len(result) == 1
        assert result[0]["tpm_used_pct"] == 0.0
        assert result[0]["rpm_used_pct"] == 0.0

    @pytest.mark.asyncio
    async def test_prune_script_failure_returns_empty(self) -> None:
        """If _ensure_prune_script fails, returns empty list."""
        budget = MagicMock()
        budget._limits = {
            "gpt-4": ModelLimits(tpm=100000, rpm=100, tpd=1000000, rpd=1000),
        }
        budget._redis = AsyncMock()
        budget._ensure_prune_script = AsyncMock(side_effect=Exception("Redis down"))

        result = await get_token_budget_status(budget)

        assert result == []
