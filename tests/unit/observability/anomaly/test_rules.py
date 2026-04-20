"""Tests for all 6 anomaly detection rules.

Each rule has:
  - positive case: anomaly detected → finding returned
  - negative case: below threshold → empty list
  - edge case where applicable (no data, boundary values)

DB is fully mocked via async_session_factory patching.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session_mock(rows: Any, *, scalar_one: Any = None, scalars: Any = None) -> tuple:
    """Return a (mock_session, mock_factory_cm) pair for patching async_session_factory.

    Args:
        rows: Value returned by ``result.all()``.
        scalar_one: Value returned by ``result.scalar_one()``.
        scalars: Value returned by ``result.scalars().all()``.

    Returns:
        Tuple of (mock_session, factory_patcher_kwargs).
    """
    mock_result = MagicMock()
    mock_result.all = MagicMock(return_value=rows)
    if scalar_one is not None:
        mock_result.scalar_one = MagicMock(return_value=scalar_one)
        mock_result.scalar_one_or_none = MagicMock(return_value=scalar_one)
    else:
        mock_result.scalar_one_or_none = MagicMock(return_value=None)

    if scalars is not None:
        scalars_proxy = MagicMock()
        scalars_proxy.all = MagicMock(return_value=scalars)
        mock_result.scalars = MagicMock(return_value=scalars_proxy)

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    return mock_session, mock_result


def _patch_factory(module_path: str, mock_session: AsyncMock):
    """Build a context-manager patch for async_session_factory at module_path.

    Args:
        module_path: Dotted path to ``async_session_factory`` in the rule module.
        mock_session: The mock session to return from ``__aenter__``.

    Returns:
        A ``patch`` context manager.
    """
    factory_mock = MagicMock()
    factory_mock.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    factory_mock.return_value.__aexit__ = AsyncMock(return_value=False)
    return patch(module_path, factory_mock)


# ---------------------------------------------------------------------------
# Rule 1: External API Error Rate
# ---------------------------------------------------------------------------


class TestExternalApiErrorRateRule:
    """Tests for ExternalApiErrorRateRule."""

    @pytest.mark.asyncio
    async def test_high_error_rate_returns_finding(self) -> None:
        """Provider with 50% error rate and 20 calls fires a finding."""
        from backend.observability.anomaly.rules.external_api_error_rate import (
            ExternalApiErrorRateRule,
        )

        row = MagicMock()
        row.provider = "openai"
        row.total_calls = 20
        row.error_calls = 10

        mock_session, _ = _make_session_mock(rows=[row])
        with _patch_factory(
            "backend.observability.anomaly.rules.external_api_error_rate.async_session_factory",
            mock_session,
        ):
            rule = ExternalApiErrorRateRule()
            findings = await rule.evaluate()

        assert len(findings) == 1
        f = findings[0]
        assert f.kind == "external_api_error_rate_elevated"
        assert f.attribution_layer == "external_api"
        assert f.evidence["provider"] == "openai"
        assert f.evidence["error_rate_pct"] == 50.0
        assert f.dedup_key == "external_api_error_rate_elevated:external_api:openai"

    @pytest.mark.asyncio
    async def test_low_error_rate_returns_empty(self) -> None:
        """Provider with 5% error rate does not fire."""
        from backend.observability.anomaly.rules.external_api_error_rate import (
            ExternalApiErrorRateRule,
        )

        row = MagicMock()
        row.provider = "yfinance"
        row.total_calls = 100
        row.error_calls = 5

        mock_session, _ = _make_session_mock(rows=[row])
        with _patch_factory(
            "backend.observability.anomaly.rules.external_api_error_rate.async_session_factory",
            mock_session,
        ):
            rule = ExternalApiErrorRateRule()
            findings = await rule.evaluate()

        assert findings == []

    @pytest.mark.asyncio
    async def test_below_min_call_count_skipped(self) -> None:
        """Provider with 50% error rate but only 5 calls does not fire (below MIN_CALL_COUNT)."""
        from backend.observability.anomaly.rules.external_api_error_rate import (
            ExternalApiErrorRateRule,
        )

        row = MagicMock()
        row.provider = "finnhub"
        row.total_calls = 5
        row.error_calls = 3

        mock_session, _ = _make_session_mock(rows=[row])
        with _patch_factory(
            "backend.observability.anomaly.rules.external_api_error_rate.async_session_factory",
            mock_session,
        ):
            rule = ExternalApiErrorRateRule()
            findings = await rule.evaluate()

        assert findings == []

    @pytest.mark.asyncio
    async def test_no_rows_returns_empty(self) -> None:
        """No rows from DB → no findings."""
        from backend.observability.anomaly.rules.external_api_error_rate import (
            ExternalApiErrorRateRule,
        )

        mock_session, _ = _make_session_mock(rows=[])
        with _patch_factory(
            "backend.observability.anomaly.rules.external_api_error_rate.async_session_factory",
            mock_session,
        ):
            rule = ExternalApiErrorRateRule()
            findings = await rule.evaluate()

        assert findings == []


# ---------------------------------------------------------------------------
# Rule 2: LLM Cost Spike
# ---------------------------------------------------------------------------


class TestLlmCostSpikeRule:
    """Tests for LlmCostSpikeRule."""

    @pytest.mark.asyncio
    async def test_cost_spike_returns_finding(self) -> None:
        """Today's cost is 4× the 7-day median → finding fires."""
        from backend.observability.anomaly.rules.llm_cost_spike import LlmCostSpikeRule

        today_cost = Decimal("4.00")

        # 7 daily rows with cost $1.00 each → median = $1.00 → ratio = 4×
        daily_row = MagicMock()
        daily_row.daily_cost = Decimal("1.00")
        daily_rows = [daily_row] * 7

        mock_result_today = MagicMock()
        mock_result_today.scalar_one = MagicMock(return_value=today_cost)

        mock_result_daily = MagicMock()
        mock_result_daily.all = MagicMock(return_value=daily_rows)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[mock_result_today, mock_result_daily])

        with _patch_factory(
            "backend.observability.anomaly.rules.llm_cost_spike.async_session_factory",
            mock_session,
        ):
            rule = LlmCostSpikeRule()
            findings = await rule.evaluate()

        assert len(findings) == 1
        f = findings[0]
        assert f.kind == "llm_cost_spike"
        assert f.attribution_layer == "llm"
        assert f.dedup_key == "llm_cost_spike:llm:daily"
        assert f.evidence["ratio"] == 4.0

    @pytest.mark.asyncio
    async def test_normal_cost_returns_empty(self) -> None:
        """Today's cost is 1.5× median → below 3× threshold → no finding."""
        from backend.observability.anomaly.rules.llm_cost_spike import LlmCostSpikeRule

        today_cost = Decimal("1.50")

        daily_row = MagicMock()
        daily_row.daily_cost = Decimal("1.00")
        daily_rows = [daily_row] * 7

        mock_result_today = MagicMock()
        mock_result_today.scalar_one = MagicMock(return_value=today_cost)

        mock_result_daily = MagicMock()
        mock_result_daily.all = MagicMock(return_value=daily_rows)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[mock_result_today, mock_result_daily])

        with _patch_factory(
            "backend.observability.anomaly.rules.llm_cost_spike.async_session_factory",
            mock_session,
        ):
            rule = LlmCostSpikeRule()
            findings = await rule.evaluate()

        assert findings == []

    @pytest.mark.asyncio
    async def test_no_baseline_data_returns_empty(self) -> None:
        """No historical daily rows → cannot compute median → no finding."""
        from backend.observability.anomaly.rules.llm_cost_spike import LlmCostSpikeRule

        mock_result_today = MagicMock()
        mock_result_today.scalar_one = MagicMock(return_value=Decimal("5.00"))

        mock_result_daily = MagicMock()
        mock_result_daily.all = MagicMock(return_value=[])

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[mock_result_today, mock_result_daily])

        with _patch_factory(
            "backend.observability.anomaly.rules.llm_cost_spike.async_session_factory",
            mock_session,
        ):
            rule = LlmCostSpikeRule()
            findings = await rule.evaluate()

        assert findings == []

    @pytest.mark.asyncio
    async def test_zero_median_with_nonzero_today_returns_finding(self) -> None:
        """Median is $0 (all past days free) but today has cost → spike fires."""
        from backend.observability.anomaly.rules.llm_cost_spike import LlmCostSpikeRule

        mock_result_today = MagicMock()
        mock_result_today.scalar_one = MagicMock(return_value=Decimal("3.00"))

        daily_row = MagicMock()
        daily_row.daily_cost = Decimal("0.00")
        daily_rows = [daily_row] * 7

        mock_result_daily = MagicMock()
        mock_result_daily.all = MagicMock(return_value=daily_rows)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[mock_result_today, mock_result_daily])

        with _patch_factory(
            "backend.observability.anomaly.rules.llm_cost_spike.async_session_factory",
            mock_session,
        ):
            rule = LlmCostSpikeRule()
            findings = await rule.evaluate()

        assert len(findings) == 1
        assert findings[0].kind == "llm_cost_spike"


# ---------------------------------------------------------------------------
# Rule 3: Slow Query Regression
# ---------------------------------------------------------------------------


class TestSlowQueryRegressionRule:
    """Tests for SlowQueryRegressionRule."""

    @pytest.mark.asyncio
    async def test_p95_regression_returns_finding(self) -> None:
        """Query hash with p95 3× baseline and 10 occurrences fires a finding."""
        from backend.observability.anomaly.rules.slow_query_regression import (
            SlowQueryRegressionRule,
        )

        query_hash = "abc123"

        # 10 recent rows with 3000ms each → p95 ≈ 3000
        recent_rows = [MagicMock(query_hash=query_hash, duration_ms=3000) for _ in range(10)]

        # 20 baseline rows with 1000ms each → p95 ≈ 1000 → ratio = 3×
        baseline_rows = [MagicMock(query_hash=query_hash, duration_ms=1000) for _ in range(20)]

        mock_result_recent = MagicMock()
        mock_result_recent.all = MagicMock(return_value=recent_rows)

        mock_result_baseline = MagicMock()
        mock_result_baseline.all = MagicMock(return_value=baseline_rows)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[mock_result_recent, mock_result_baseline])

        with _patch_factory(
            "backend.observability.anomaly.rules.slow_query_regression.async_session_factory",
            mock_session,
        ):
            rule = SlowQueryRegressionRule()
            findings = await rule.evaluate()

        assert len(findings) == 1
        f = findings[0]
        assert f.kind == "slow_query_regression"
        assert f.attribution_layer == "db"
        assert f.evidence["query_hash"] == query_hash
        assert f.dedup_key == f"slow_query_regression:db:{query_hash}"

    @pytest.mark.asyncio
    async def test_below_regression_threshold_returns_empty(self) -> None:
        """Query with p95 only 1.5× baseline does not fire."""
        from backend.observability.anomaly.rules.slow_query_regression import (
            SlowQueryRegressionRule,
        )

        query_hash = "def456"

        recent_rows = [MagicMock(query_hash=query_hash, duration_ms=1500) for _ in range(10)]
        baseline_rows = [MagicMock(query_hash=query_hash, duration_ms=1000) for _ in range(10)]

        mock_result_recent = MagicMock()
        mock_result_recent.all = MagicMock(return_value=recent_rows)

        mock_result_baseline = MagicMock()
        mock_result_baseline.all = MagicMock(return_value=baseline_rows)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[mock_result_recent, mock_result_baseline])

        with _patch_factory(
            "backend.observability.anomaly.rules.slow_query_regression.async_session_factory",
            mock_session,
        ):
            rule = SlowQueryRegressionRule()
            findings = await rule.evaluate()

        assert findings == []

    @pytest.mark.asyncio
    async def test_below_min_occurrences_skipped(self) -> None:
        """Query hash with only 3 recent rows (below MIN_OCCURRENCES=5) is skipped."""
        from backend.observability.anomaly.rules.slow_query_regression import (
            SlowQueryRegressionRule,
        )

        query_hash = "ghi789"

        recent_rows = [MagicMock(query_hash=query_hash, duration_ms=9000) for _ in range(3)]
        baseline_rows = [MagicMock(query_hash=query_hash, duration_ms=1000) for _ in range(20)]

        mock_result_recent = MagicMock()
        mock_result_recent.all = MagicMock(return_value=recent_rows)

        mock_result_baseline = MagicMock()
        mock_result_baseline.all = MagicMock(return_value=baseline_rows)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[mock_result_recent, mock_result_baseline])

        with _patch_factory(
            "backend.observability.anomaly.rules.slow_query_regression.async_session_factory",
            mock_session,
        ):
            rule = SlowQueryRegressionRule()
            findings = await rule.evaluate()

        assert findings == []

    @pytest.mark.asyncio
    async def test_no_baseline_for_hash_skipped(self) -> None:
        """New query hash with no baseline data is skipped."""
        from backend.observability.anomaly.rules.slow_query_regression import (
            SlowQueryRegressionRule,
        )

        query_hash = "newquery"

        recent_rows = [MagicMock(query_hash=query_hash, duration_ms=5000) for _ in range(10)]

        mock_result_recent = MagicMock()
        mock_result_recent.all = MagicMock(return_value=recent_rows)

        mock_result_baseline = MagicMock()
        mock_result_baseline.all = MagicMock(return_value=[])

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[mock_result_recent, mock_result_baseline])

        with _patch_factory(
            "backend.observability.anomaly.rules.slow_query_regression.async_session_factory",
            mock_session,
        ):
            rule = SlowQueryRegressionRule()
            findings = await rule.evaluate()

        assert findings == []


# ---------------------------------------------------------------------------
# Rule 4: DB Pool Exhaustion
# ---------------------------------------------------------------------------


class TestDbPoolExhaustionRule:
    """Tests for DbPoolExhaustionRule."""

    @pytest.mark.asyncio
    async def test_exhaustion_event_returns_finding(self) -> None:
        """A recent pool exhaustion event fires a critical finding."""
        from backend.observability.anomaly.rules.db_pool_exhaustion import DbPoolExhaustionRule

        event = MagicMock()
        event.id = "uuid-pool-1"
        event.ts = datetime.now(timezone.utc)
        event.pool_size = 10
        event.checked_out = 10
        event.overflow = 5

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=event)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with _patch_factory(
            "backend.observability.anomaly.rules.db_pool_exhaustion.async_session_factory",
            mock_session,
        ):
            rule = DbPoolExhaustionRule()
            findings = await rule.evaluate()

        assert len(findings) == 1
        f = findings[0]
        assert f.kind == "db_pool_exhaustion"
        assert f.severity == "critical"
        assert f.attribution_layer == "db"
        assert f.dedup_key == "db_pool_exhaustion:db:pool"

    @pytest.mark.asyncio
    async def test_no_exhaustion_event_returns_empty(self) -> None:
        """No exhaustion events in the window → no finding."""
        from backend.observability.anomaly.rules.db_pool_exhaustion import DbPoolExhaustionRule

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with _patch_factory(
            "backend.observability.anomaly.rules.db_pool_exhaustion.async_session_factory",
            mock_session,
        ):
            rule = DbPoolExhaustionRule()
            findings = await rule.evaluate()

        assert findings == []


# ---------------------------------------------------------------------------
# Rule 5: Rate Limiter Fallback
# ---------------------------------------------------------------------------


class TestRateLimiterFallbackRule:
    """Tests for RateLimiterFallbackRule."""

    @pytest.mark.asyncio
    async def test_fallback_event_returns_finding(self) -> None:
        """A fallback_permissive event fires a warning finding."""
        from backend.observability.anomaly.rules.rate_limiter_fallback import (
            RateLimiterFallbackRule,
        )

        event = MagicMock()
        event.limiter_name = "openai_chat"
        event.ts = datetime.now(timezone.utc)
        event.reason_if_fallback = "Redis unavailable"

        scalars_proxy = MagicMock()
        scalars_proxy.all = MagicMock(return_value=[event])

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=scalars_proxy)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with _patch_factory(
            "backend.observability.anomaly.rules.rate_limiter_fallback.async_session_factory",
            mock_session,
        ):
            rule = RateLimiterFallbackRule()
            findings = await rule.evaluate()

        assert len(findings) == 1
        f = findings[0]
        assert f.kind == "rate_limiter_fallback"
        assert f.attribution_layer == "rate_limiter"
        assert f.dedup_key == "rate_limiter_fallback:rate_limiter:openai_chat"

    @pytest.mark.asyncio
    async def test_no_fallback_events_returns_empty(self) -> None:
        """No fallback events in window → no finding."""
        from backend.observability.anomaly.rules.rate_limiter_fallback import (
            RateLimiterFallbackRule,
        )

        scalars_proxy = MagicMock()
        scalars_proxy.all = MagicMock(return_value=[])

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=scalars_proxy)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with _patch_factory(
            "backend.observability.anomaly.rules.rate_limiter_fallback.async_session_factory",
            mock_session,
        ):
            rule = RateLimiterFallbackRule()
            findings = await rule.evaluate()

        assert findings == []

    @pytest.mark.asyncio
    async def test_multiple_events_same_limiter_deduplicated(self) -> None:
        """Multiple fallback events for the same limiter produce exactly one finding."""
        from backend.observability.anomaly.rules.rate_limiter_fallback import (
            RateLimiterFallbackRule,
        )

        now = datetime.now(timezone.utc)
        events = []
        for i in range(3):
            evt = MagicMock()
            evt.limiter_name = "yfinance"
            evt.ts = now - timedelta(seconds=i * 30)
            evt.reason_if_fallback = "Redis timeout"
            events.append(evt)

        scalars_proxy = MagicMock()
        scalars_proxy.all = MagicMock(return_value=events)

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=scalars_proxy)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with _patch_factory(
            "backend.observability.anomaly.rules.rate_limiter_fallback.async_session_factory",
            mock_session,
        ):
            rule = RateLimiterFallbackRule()
            findings = await rule.evaluate()

        assert len(findings) == 1
        assert findings[0].evidence["limiter_name"] == "yfinance"

    @pytest.mark.asyncio
    async def test_multiple_distinct_limiters_each_get_finding(self) -> None:
        """Two different limiters in fallback mode produce two distinct findings."""
        from backend.observability.anomaly.rules.rate_limiter_fallback import (
            RateLimiterFallbackRule,
        )

        now = datetime.now(timezone.utc)
        events = []
        for limiter in ("openai_chat", "yfinance"):
            evt = MagicMock()
            evt.limiter_name = limiter
            evt.ts = now
            evt.reason_if_fallback = "Redis unavailable"
            events.append(evt)

        scalars_proxy = MagicMock()
        scalars_proxy.all = MagicMock(return_value=events)

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=scalars_proxy)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with _patch_factory(
            "backend.observability.anomaly.rules.rate_limiter_fallback.async_session_factory",
            mock_session,
        ):
            rule = RateLimiterFallbackRule()
            findings = await rule.evaluate()

        assert len(findings) == 2
        dedup_keys = {f.dedup_key for f in findings}
        assert "rate_limiter_fallback:rate_limiter:openai_chat" in dedup_keys
        assert "rate_limiter_fallback:rate_limiter:yfinance" in dedup_keys


# ---------------------------------------------------------------------------
# Rule 6: Watermark Staleness
# ---------------------------------------------------------------------------


class TestWatermarkStalenessRule:
    """Tests for WatermarkStalenessRule."""

    @pytest.mark.asyncio
    async def test_stale_watermark_returns_finding(self) -> None:
        """Pipeline last ran 3 days ago (cadence 24h → stale at 48h) → finding fires."""
        from backend.observability.anomaly.rules.watermark_staleness import WatermarkStalenessRule

        now = datetime.now(timezone.utc)
        wm = MagicMock()
        wm.pipeline_name = "nightly_price_refresh"
        wm.last_completed_at = now - timedelta(hours=73)  # 3+ days ago
        wm.status = "ok"

        scalars_proxy = MagicMock()
        scalars_proxy.all = MagicMock(return_value=[wm])

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=scalars_proxy)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with _patch_factory(
            "backend.observability.anomaly.rules.watermark_staleness.async_session_factory",
            mock_session,
        ):
            rule = WatermarkStalenessRule()
            findings = await rule.evaluate()

        assert len(findings) == 1
        f = findings[0]
        assert f.kind == "watermark_stale"
        assert f.attribution_layer == "pipeline"
        assert f.evidence["pipeline_name"] == "nightly_price_refresh"
        assert f.dedup_key == "watermark_stale:pipeline:nightly_price_refresh"

    @pytest.mark.asyncio
    async def test_fresh_watermark_returns_empty(self) -> None:
        """Pipeline ran 12 hours ago (cadence 24h → stale at 48h) → no finding."""
        from backend.observability.anomaly.rules.watermark_staleness import WatermarkStalenessRule

        now = datetime.now(timezone.utc)
        wm = MagicMock()
        wm.pipeline_name = "nightly_price_refresh"
        wm.last_completed_at = now - timedelta(hours=12)
        wm.status = "ok"

        scalars_proxy = MagicMock()
        scalars_proxy.all = MagicMock(return_value=[wm])

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=scalars_proxy)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with _patch_factory(
            "backend.observability.anomaly.rules.watermark_staleness.async_session_factory",
            mock_session,
        ):
            rule = WatermarkStalenessRule()
            findings = await rule.evaluate()

        assert findings == []

    @pytest.mark.asyncio
    async def test_no_watermarks_returns_empty(self) -> None:
        """No watermarks in DB → no findings."""
        from backend.observability.anomaly.rules.watermark_staleness import WatermarkStalenessRule

        scalars_proxy = MagicMock()
        scalars_proxy.all = MagicMock(return_value=[])

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=scalars_proxy)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with _patch_factory(
            "backend.observability.anomaly.rules.watermark_staleness.async_session_factory",
            mock_session,
        ):
            rule = WatermarkStalenessRule()
            findings = await rule.evaluate()

        assert findings == []

    @pytest.mark.asyncio
    async def test_tz_naive_timestamp_handled(self) -> None:
        """Timezone-naive last_completed_at is treated as UTC without crashing."""
        from backend.observability.anomaly.rules.watermark_staleness import WatermarkStalenessRule

        # tz-naive timestamp 3 days old
        naive_ts = datetime.utcnow() - timedelta(hours=73)

        wm = MagicMock()
        wm.pipeline_name = "nightly_price_refresh"
        wm.last_completed_at = naive_ts
        wm.status = "ok"

        scalars_proxy = MagicMock()
        scalars_proxy.all = MagicMock(return_value=[wm])

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=scalars_proxy)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with _patch_factory(
            "backend.observability.anomaly.rules.watermark_staleness.async_session_factory",
            mock_session,
        ):
            rule = WatermarkStalenessRule()
            findings = await rule.evaluate()

        assert len(findings) == 1
        assert findings[0].kind == "watermark_stale"


# ---------------------------------------------------------------------------
# Registry sanity check
# ---------------------------------------------------------------------------


class TestRuleRegistry:
    """Verifies the ALL_RULES registry is populated correctly."""

    def test_all_rules_list_has_twelve_entries(self) -> None:
        """ALL_RULES registry contains exactly 12 rule instances."""
        from backend.observability.anomaly.rules import ALL_RULES

        assert len(ALL_RULES) == 12

    def test_all_rules_are_anomaly_rule_instances(self) -> None:
        """Every entry in ALL_RULES is an AnomalyRule subclass instance."""
        from backend.observability.anomaly.base import AnomalyRule
        from backend.observability.anomaly.rules import ALL_RULES

        for rule in ALL_RULES:
            assert isinstance(rule, AnomalyRule), f"{rule!r} is not an AnomalyRule"

    def test_rule_names_are_unique(self) -> None:
        """All rule names in ALL_RULES are distinct."""
        from backend.observability.anomaly.rules import ALL_RULES

        names = [r.name for r in ALL_RULES]
        assert len(names) == len(set(names)), "Duplicate rule names detected"


# ---------------------------------------------------------------------------
# Rule 7: Worker Heartbeat Missing
# ---------------------------------------------------------------------------


class TestWorkerHeartbeatMissingRule:
    """Tests for WorkerHeartbeatMissingRule."""

    @pytest.mark.asyncio
    async def test_stale_worker_returns_finding(self) -> None:
        """Worker with last heartbeat >90s ago fires a finding."""
        from backend.observability.anomaly.rules.worker_heartbeat_missing import (
            WorkerHeartbeatMissingRule,
        )

        now = datetime.now(timezone.utc)
        # Two distinct workers: one stale, one fresh
        row_stale = MagicMock()
        row_stale.worker_name = "celery@worker-1"
        row_stale.latest_ts = now - timedelta(seconds=120)
        row_stale.status = "alive"

        row_fresh = MagicMock()
        row_fresh.worker_name = "celery@worker-2"
        row_fresh.latest_ts = now - timedelta(seconds=30)
        row_fresh.status = "alive"

        mock_session, _ = _make_session_mock(rows=[row_stale, row_fresh])
        with _patch_factory(
            "backend.observability.anomaly.rules.worker_heartbeat_missing.async_session_factory",
            mock_session,
        ):
            rule = WorkerHeartbeatMissingRule()
            findings = await rule.evaluate()

        assert len(findings) == 1
        f = findings[0]
        assert f.kind == "worker_heartbeat_missing"
        assert f.attribution_layer == "celery"
        assert f.severity == "error"
        assert "celery@worker-1" in f.title
        assert f.dedup_key == "worker_heartbeat_missing:celery:celery@worker-1"

    @pytest.mark.asyncio
    async def test_shutdown_worker_is_skipped(self) -> None:
        """Worker that gracefully shut down does not fire a finding."""
        from backend.observability.anomaly.rules.worker_heartbeat_missing import (
            WorkerHeartbeatMissingRule,
        )

        now = datetime.now(timezone.utc)
        row = MagicMock()
        row.worker_name = "celery@worker-1"
        row.latest_ts = now - timedelta(seconds=120)
        row.status = "shutdown"

        mock_session, _ = _make_session_mock(rows=[row])
        with _patch_factory(
            "backend.observability.anomaly.rules.worker_heartbeat_missing.async_session_factory",
            mock_session,
        ):
            rule = WorkerHeartbeatMissingRule()
            findings = await rule.evaluate()

        assert findings == []

    @pytest.mark.asyncio
    async def test_all_workers_fresh_returns_empty(self) -> None:
        """All workers heartbeated recently → no findings."""
        from backend.observability.anomaly.rules.worker_heartbeat_missing import (
            WorkerHeartbeatMissingRule,
        )

        now = datetime.now(timezone.utc)
        row = MagicMock()
        row.worker_name = "celery@worker-1"
        row.latest_ts = now - timedelta(seconds=30)
        row.status = "alive"

        mock_session, _ = _make_session_mock(rows=[row])
        with _patch_factory(
            "backend.observability.anomaly.rules.worker_heartbeat_missing.async_session_factory",
            mock_session,
        ):
            rule = WorkerHeartbeatMissingRule()
            findings = await rule.evaluate()

        assert findings == []

    @pytest.mark.asyncio
    async def test_no_heartbeats_returns_empty(self) -> None:
        """No heartbeat rows at all → no findings (no known workers)."""
        from backend.observability.anomaly.rules.worker_heartbeat_missing import (
            WorkerHeartbeatMissingRule,
        )

        mock_session, _ = _make_session_mock(rows=[])
        with _patch_factory(
            "backend.observability.anomaly.rules.worker_heartbeat_missing.async_session_factory",
            mock_session,
        ):
            rule = WorkerHeartbeatMissingRule()
            findings = await rule.evaluate()

        assert findings == []


# ---------------------------------------------------------------------------
# Rule 8: Beat Schedule Drift
# ---------------------------------------------------------------------------


class TestBeatScheduleDriftRule:
    """Tests for BeatScheduleDriftRule."""

    @pytest.mark.asyncio
    async def test_high_drift_returns_finding(self) -> None:
        """Beat run with drift >300s fires a finding."""
        from backend.observability.anomaly.rules.beat_schedule_drift import (
            BeatScheduleDriftRule,
        )

        row = MagicMock()
        row.task_name = "backend.tasks.nightly_chain"
        row.drift_seconds = 450.0
        row.ts = datetime.now(timezone.utc) - timedelta(minutes=10)
        row.outcome = "dispatched"

        mock_session, _ = _make_session_mock(rows=[], scalars=[row])
        with _patch_factory(
            "backend.observability.anomaly.rules.beat_schedule_drift.async_session_factory",
            mock_session,
        ):
            rule = BeatScheduleDriftRule()
            findings = await rule.evaluate()

        assert len(findings) == 1
        f = findings[0]
        assert f.kind == "beat_schedule_drift"
        assert f.attribution_layer == "celery"
        assert f.severity == "warning"
        assert "nightly_chain" in f.title
        assert f.dedup_key == "beat_schedule_drift:celery:backend.tasks.nightly_chain"

    @pytest.mark.asyncio
    async def test_no_drifting_runs_returns_empty(self) -> None:
        """No beat runs exceeding drift threshold → no findings (SQL WHERE filters)."""
        from backend.observability.anomaly.rules.beat_schedule_drift import (
            BeatScheduleDriftRule,
        )

        mock_session, _ = _make_session_mock(rows=[], scalars=[])
        with _patch_factory(
            "backend.observability.anomaly.rules.beat_schedule_drift.async_session_factory",
            mock_session,
        ):
            rule = BeatScheduleDriftRule()
            findings = await rule.evaluate()

        assert findings == []

    @pytest.mark.asyncio
    async def test_no_beat_runs_returns_empty(self) -> None:
        """No beat schedule runs in window → no findings."""
        from backend.observability.anomaly.rules.beat_schedule_drift import (
            BeatScheduleDriftRule,
        )

        mock_session, _ = _make_session_mock(rows=[], scalars=[])
        with _patch_factory(
            "backend.observability.anomaly.rules.beat_schedule_drift.async_session_factory",
            mock_session,
        ):
            rule = BeatScheduleDriftRule()
            findings = await rule.evaluate()

        assert findings == []


# ---------------------------------------------------------------------------
# Rule 9: 5xx Rate Elevated
# ---------------------------------------------------------------------------


class TestHttp5xxElevatedRule:
    """Tests for Http5xxElevatedRule."""

    @pytest.mark.asyncio
    async def test_above_threshold_returns_finding(self) -> None:
        """More than 5 5xx errors in 5min fires a finding."""
        from backend.observability.anomaly.rules.http_5xx_elevated import (
            Http5xxElevatedRule,
        )

        mock_session, mock_result = _make_session_mock(rows=[], scalar_one=8)
        with _patch_factory(
            "backend.observability.anomaly.rules.http_5xx_elevated.async_session_factory",
            mock_session,
        ):
            rule = Http5xxElevatedRule()
            findings = await rule.evaluate()

        assert len(findings) == 1
        f = findings[0]
        assert f.kind == "http_5xx_elevated"
        assert f.attribution_layer == "api"
        assert f.severity == "error"
        assert f.evidence["count_5xx"] == 8
        assert f.dedup_key == "http_5xx_elevated:api:all"

    @pytest.mark.asyncio
    async def test_below_threshold_returns_empty(self) -> None:
        """3 5xx errors in 5min does not fire (threshold is >5)."""
        from backend.observability.anomaly.rules.http_5xx_elevated import (
            Http5xxElevatedRule,
        )

        mock_session, mock_result = _make_session_mock(rows=[], scalar_one=3)
        with _patch_factory(
            "backend.observability.anomaly.rules.http_5xx_elevated.async_session_factory",
            mock_session,
        ):
            rule = Http5xxElevatedRule()
            findings = await rule.evaluate()

        assert findings == []

    @pytest.mark.asyncio
    async def test_zero_errors_returns_empty(self) -> None:
        """Zero 5xx errors → no finding."""
        from backend.observability.anomaly.rules.http_5xx_elevated import (
            Http5xxElevatedRule,
        )

        mock_session, mock_result = _make_session_mock(rows=[], scalar_one=0)
        with _patch_factory(
            "backend.observability.anomaly.rules.http_5xx_elevated.async_session_factory",
            mock_session,
        ):
            rule = Http5xxElevatedRule()
            findings = await rule.evaluate()

        assert findings == []


# ---------------------------------------------------------------------------
# Rule 10: Frontend Error Burst
# ---------------------------------------------------------------------------


class TestFrontendErrorBurstRule:
    """Tests for FrontendErrorBurstRule."""

    @pytest.mark.asyncio
    async def test_burst_above_threshold_returns_finding(self) -> None:
        """25 react_error_boundary errors in 5min fires a finding."""
        from backend.observability.anomaly.rules.frontend_error_burst import (
            FrontendErrorBurstRule,
        )

        row = MagicMock()
        row.error_type = "react_error_boundary"
        row.error_count = 25

        mock_session, _ = _make_session_mock(rows=[row])
        with _patch_factory(
            "backend.observability.anomaly.rules.frontend_error_burst.async_session_factory",
            mock_session,
        ):
            rule = FrontendErrorBurstRule()
            findings = await rule.evaluate()

        assert len(findings) == 1
        f = findings[0]
        assert f.kind == "frontend_error_burst"
        assert f.attribution_layer == "frontend"
        assert f.severity == "warning"
        assert "react_error_boundary" in f.title
        assert f.dedup_key == "frontend_error_burst:frontend:react_error_boundary"

    @pytest.mark.asyncio
    async def test_below_threshold_returns_empty(self) -> None:
        """10 errors of same type in 5min does not fire (threshold is >20)."""
        from backend.observability.anomaly.rules.frontend_error_burst import (
            FrontendErrorBurstRule,
        )

        row = MagicMock()
        row.error_type = "unhandled_rejection"
        row.error_count = 10

        mock_session, _ = _make_session_mock(rows=[row])
        with _patch_factory(
            "backend.observability.anomaly.rules.frontend_error_burst.async_session_factory",
            mock_session,
        ):
            rule = FrontendErrorBurstRule()
            findings = await rule.evaluate()

        assert findings == []

    @pytest.mark.asyncio
    async def test_no_frontend_errors_returns_empty(self) -> None:
        """No frontend error rows → no findings."""
        from backend.observability.anomaly.rules.frontend_error_burst import (
            FrontendErrorBurstRule,
        )

        mock_session, _ = _make_session_mock(rows=[])
        with _patch_factory(
            "backend.observability.anomaly.rules.frontend_error_burst.async_session_factory",
            mock_session,
        ):
            rule = FrontendErrorBurstRule()
            findings = await rule.evaluate()

        assert findings == []


# ---------------------------------------------------------------------------
# Rule 11: DQ Critical Findings
# ---------------------------------------------------------------------------


class TestDqCriticalFindingsRule:
    """Tests for DqCriticalFindingsRule."""

    @pytest.mark.asyncio
    async def test_critical_dq_returns_finding(self) -> None:
        """Critical DQ check in the last run fires a finding."""
        from backend.observability.anomaly.rules.dq_critical_findings import (
            DqCriticalFindingsRule,
        )

        now = datetime.now(timezone.utc)
        row = MagicMock()
        row.check_name = "price_gap_check"
        row.severity = "critical"
        row.ticker = "AAPL"
        row.message = "Price gap > 50% detected"
        row.detected_at = now - timedelta(minutes=3)

        mock_session, _ = _make_session_mock(rows=[], scalars=[row])
        with _patch_factory(
            "backend.observability.anomaly.rules.dq_critical_findings.async_session_factory",
            mock_session,
        ):
            rule = DqCriticalFindingsRule()
            findings = await rule.evaluate()

        assert len(findings) == 1
        f = findings[0]
        assert f.kind == "dq_critical"
        assert f.attribution_layer == "data_quality"
        assert f.severity == "critical"
        assert "price_gap_check" in f.title
        assert f.dedup_key == "dq_critical:data_quality:price_gap_check"

    @pytest.mark.asyncio
    async def test_no_critical_findings_returns_empty(self) -> None:
        """No critical DQ checks in window → no findings (SQL WHERE filters)."""
        from backend.observability.anomaly.rules.dq_critical_findings import (
            DqCriticalFindingsRule,
        )

        mock_session, _ = _make_session_mock(rows=[], scalars=[])
        with _patch_factory(
            "backend.observability.anomaly.rules.dq_critical_findings.async_session_factory",
            mock_session,
        ):
            rule = DqCriticalFindingsRule()
            findings = await rule.evaluate()

        assert findings == []


# ---------------------------------------------------------------------------
# Rule 12: Agent Decline Rate Elevated
# ---------------------------------------------------------------------------


class TestAgentDeclineRateRule:
    """Tests for AgentDeclineRateRule."""

    @pytest.mark.asyncio
    async def test_high_decline_rate_returns_finding(self) -> None:
        """Decline rate >10% with ≥20 queries fires a finding."""
        from backend.observability.anomaly.rules.agent_decline_rate import (
            AgentDeclineRateRule,
        )

        row = MagicMock()
        row.total_queries = 100
        row.declined_queries = 15

        mock_session, mock_result = _make_session_mock(rows=[])
        mock_result.one = MagicMock(return_value=row)
        with _patch_factory(
            "backend.observability.anomaly.rules.agent_decline_rate.async_session_factory",
            mock_session,
        ):
            rule = AgentDeclineRateRule()
            findings = await rule.evaluate()

        assert len(findings) == 1
        f = findings[0]
        assert f.kind == "agent_decline_rate_elevated"
        assert f.attribution_layer == "agent"
        assert f.severity == "warning"
        assert f.evidence["decline_rate_pct"] == 15.0
        assert f.dedup_key == "agent_decline_rate_elevated:agent:all"

    @pytest.mark.asyncio
    async def test_low_decline_rate_returns_empty(self) -> None:
        """Decline rate at 5% does not fire."""
        from backend.observability.anomaly.rules.agent_decline_rate import (
            AgentDeclineRateRule,
        )

        row = MagicMock()
        row.total_queries = 100
        row.declined_queries = 5

        mock_session, mock_result = _make_session_mock(rows=[])
        mock_result.one = MagicMock(return_value=row)
        with _patch_factory(
            "backend.observability.anomaly.rules.agent_decline_rate.async_session_factory",
            mock_session,
        ):
            rule = AgentDeclineRateRule()
            findings = await rule.evaluate()

        assert findings == []

    @pytest.mark.asyncio
    async def test_low_volume_skipped(self) -> None:
        """Fewer than 20 total queries → skip (insufficient sample)."""
        from backend.observability.anomaly.rules.agent_decline_rate import (
            AgentDeclineRateRule,
        )

        row = MagicMock()
        row.total_queries = 10
        row.declined_queries = 5

        mock_session, mock_result = _make_session_mock(rows=[])
        mock_result.one = MagicMock(return_value=row)
        with _patch_factory(
            "backend.observability.anomaly.rules.agent_decline_rate.async_session_factory",
            mock_session,
        ):
            rule = AgentDeclineRateRule()
            findings = await rule.evaluate()

        assert findings == []

    @pytest.mark.asyncio
    async def test_no_intent_rows_returns_empty(self) -> None:
        """Zero queries in window → no findings (below MIN_QUERY_COUNT)."""
        from backend.observability.anomaly.rules.agent_decline_rate import (
            AgentDeclineRateRule,
        )

        row = MagicMock()
        row.total_queries = 0
        row.declined_queries = 0

        mock_session, mock_result = _make_session_mock(rows=[])
        mock_result.one = MagicMock(return_value=row)
        with _patch_factory(
            "backend.observability.anomaly.rules.agent_decline_rate.async_session_factory",
            mock_session,
        ):
            rule = AgentDeclineRateRule()
            findings = await rule.evaluate()

        assert findings == []
