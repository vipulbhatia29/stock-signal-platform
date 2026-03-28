"""Tests for ObservabilityCollector — DB-backed reads + fire-and-forget writes."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.agents.observability import ObservabilityCollector


@pytest.fixture
def collector_with_writer():
    """Return (collector, mock_writer) pair with writer injected."""
    collector = ObservabilityCollector()
    writer = AsyncMock()
    collector.set_db_writer(writer)
    return collector, writer


class _FakeRow:
    """Fake SA result row with attribute access."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class TestGetStats:
    """Tests for DB-backed get_stats()."""

    @pytest.mark.asyncio
    async def test_get_stats_empty_db(self) -> None:
        """Empty DB returns zero counts."""
        collector = ObservabilityCollector()
        db = AsyncMock()

        # 4 queries: requests_by_model, cascades_by_model, rpm_by_model
        empty_result = MagicMock()
        empty_result.all.return_value = []
        db.execute = AsyncMock(return_value=empty_result)

        stats = await collector.get_stats(db)
        assert stats["requests_by_model"] == {}
        assert stats["cascade_count"] == 0
        assert stats["cascades_by_model"] == {}
        assert stats["rpm_by_model"] == {}
        assert stats["cascade_log"] == []

    @pytest.mark.asyncio
    async def test_get_stats_with_data(self) -> None:
        """Stats reflect DB query results."""
        collector = ObservabilityCollector()
        db = AsyncMock()

        # Simulate 3 sequential queries
        req_result = MagicMock()
        req_result.all.return_value = [_FakeRow(model="llama-70b", cnt=10)]
        casc_result = MagicMock()
        casc_result.all.return_value = [_FakeRow(model="llama-70b", cnt=2)]
        rpm_result = MagicMock()
        rpm_result.all.return_value = [_FakeRow(model="llama-70b", cnt=5)]

        db.execute = AsyncMock(side_effect=[req_result, casc_result, rpm_result])

        stats = await collector.get_stats(db)
        assert stats["requests_by_model"]["llama-70b"] == 10
        assert stats["cascade_count"] == 2
        assert stats["cascades_by_model"]["llama-70b"] == 2
        assert stats["rpm_by_model"]["llama-70b"] == 5


class TestGetTierHealth:
    """Tests for DB-backed tier health classification."""

    @pytest.mark.asyncio
    async def test_healthy_no_failures(self) -> None:
        """A model with only successes in the last 5 min is 'healthy'."""
        collector = ObservabilityCollector()
        db = AsyncMock()

        fail_result = MagicMock()
        fail_result.all.return_value = []
        succ_result = MagicMock()
        succ_result.all.return_value = [_FakeRow(model="llama-70b", cnt=5)]
        lat_result = MagicMock()
        lat_result.all.return_value = [_FakeRow(model="llama-70b", avg_ms=100, p95_ms=150)]
        casc_result = MagicMock()
        casc_result.all.return_value = []

        db.execute = AsyncMock(side_effect=[fail_result, succ_result, lat_result, casc_result])

        health = await collector.get_tier_health(db)
        entry = next(t for t in health["tiers"] if t["model"] == "llama-70b")
        assert entry["status"] == "healthy"
        assert entry["successes_5m"] == 5

    @pytest.mark.asyncio
    async def test_degraded_few_failures(self) -> None:
        """A model with 1-3 recent failures is 'degraded'."""
        collector = ObservabilityCollector()
        db = AsyncMock()

        fail_result = MagicMock()
        fail_result.all.return_value = [_FakeRow(model="llama-70b", cnt=2)]
        succ_result = MagicMock()
        succ_result.all.return_value = [_FakeRow(model="llama-70b", cnt=5)]
        lat_result = MagicMock()
        lat_result.all.return_value = [_FakeRow(model="llama-70b", avg_ms=100, p95_ms=150)]
        casc_result = MagicMock()
        casc_result.all.return_value = [_FakeRow(model="llama-70b", cnt=2)]

        db.execute = AsyncMock(side_effect=[fail_result, succ_result, lat_result, casc_result])

        health = await collector.get_tier_health(db)
        entry = next(t for t in health["tiers"] if t["model"] == "llama-70b")
        assert entry["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_down_many_failures(self) -> None:
        """A model with 4+ recent failures is 'down'."""
        collector = ObservabilityCollector()
        db = AsyncMock()

        fail_result = MagicMock()
        fail_result.all.return_value = [_FakeRow(model="llama-70b", cnt=5)]
        succ_result = MagicMock()
        succ_result.all.return_value = []
        lat_result = MagicMock()
        lat_result.all.return_value = []
        casc_result = MagicMock()
        casc_result.all.return_value = [_FakeRow(model="llama-70b", cnt=5)]

        db.execute = AsyncMock(side_effect=[fail_result, succ_result, lat_result, casc_result])

        health = await collector.get_tier_health(db)
        entry = next(t for t in health["tiers"] if t["model"] == "llama-70b")
        assert entry["status"] == "down"

    @pytest.mark.asyncio
    async def test_disabled_status(self) -> None:
        """A manually disabled model shows 'disabled' regardless of DB data."""
        collector = ObservabilityCollector()
        collector.toggle_model("llama-70b", enabled=False)
        db = AsyncMock()

        fail_result = MagicMock()
        fail_result.all.return_value = []
        succ_result = MagicMock()
        succ_result.all.return_value = []
        lat_result = MagicMock()
        lat_result.all.return_value = []
        casc_result = MagicMock()
        casc_result.all.return_value = []

        db.execute = AsyncMock(side_effect=[fail_result, succ_result, lat_result, casc_result])

        health = await collector.get_tier_health(db)
        entry = next(t for t in health["tiers"] if t["model"] == "llama-70b")
        assert entry["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_health_summary_counts(self) -> None:
        """Health summary counts models by status."""
        collector = ObservabilityCollector()
        collector.toggle_model("model-b", enabled=False)
        db = AsyncMock()

        fail_result = MagicMock()
        fail_result.all.return_value = []
        succ_result = MagicMock()
        succ_result.all.return_value = [_FakeRow(model="model-a", cnt=3)]
        lat_result = MagicMock()
        lat_result.all.return_value = [_FakeRow(model="model-a", avg_ms=100, p95_ms=150)]
        casc_result = MagicMock()
        casc_result.all.return_value = []

        db.execute = AsyncMock(side_effect=[fail_result, succ_result, lat_result, casc_result])

        health = await collector.get_tier_health(db)
        assert health["summary"]["total"] == 2
        assert health["summary"]["healthy"] == 1
        assert health["summary"]["disabled"] == 1


class TestToggleModel:
    """Tests for model enable/disable (still in-memory)."""

    def test_toggle_disable(self) -> None:
        """Disabling a model adds it to disabled set."""
        collector = ObservabilityCollector()
        collector.toggle_model("llama-70b", enabled=False)
        assert "llama-70b" in collector._disabled_models

    def test_toggle_enable(self) -> None:
        """Re-enabling a model removes it from disabled set."""
        collector = ObservabilityCollector()
        collector.toggle_model("llama-70b", enabled=False)
        collector.toggle_model("llama-70b", enabled=True)
        assert "llama-70b" not in collector._disabled_models


class TestFallbackRate:
    """Tests for DB-backed fallback_rate_last_60s()."""

    @pytest.mark.asyncio
    async def test_fallback_rate_empty(self) -> None:
        """No data returns 0.0."""
        collector = ObservabilityCollector()
        db = AsyncMock()
        result = MagicMock()
        result.one.return_value = _FakeRow(total=0, failures=0)
        db.execute = AsyncMock(return_value=result)

        assert await collector.fallback_rate_last_60s(db) == 0.0

    @pytest.mark.asyncio
    async def test_fallback_rate_all_success(self) -> None:
        """Only successes returns 0.0."""
        collector = ObservabilityCollector()
        db = AsyncMock()
        result = MagicMock()
        result.one.return_value = _FakeRow(total=10, failures=0)
        db.execute = AsyncMock(return_value=result)

        assert await collector.fallback_rate_last_60s(db) == 0.0

    @pytest.mark.asyncio
    async def test_fallback_rate_mixed(self) -> None:
        """3 failures + 7 successes returns 0.3."""
        collector = ObservabilityCollector()
        db = AsyncMock()
        result = MagicMock()
        result.one.return_value = _FakeRow(total=10, failures=3)
        db.execute = AsyncMock(return_value=result)

        rate = await collector.fallback_rate_last_60s(db)
        assert abs(rate - 0.3) < 0.01


class TestRecordCascadeLog:
    """Tests for in-memory cascade log (kept for admin debugging)."""

    @pytest.mark.asyncio
    async def test_cascade_appended_to_log(self) -> None:
        """Cascade events appear in the in-memory cascade log."""
        collector = ObservabilityCollector()
        await collector.record_cascade(
            from_model="llama-70b",
            reason="rate_limit",
            provider="groq",
            tier="planner",
        )
        assert len(collector._cascade_log) == 1
        assert collector._cascade_log[0]["model"] == "llama-70b"
        assert collector._cascade_log[0]["reason"] == "rate_limit"


class TestLoopStepPassthrough:
    """Tests for loop_step parameter propagation through the collector."""

    @pytest.mark.asyncio
    async def test_record_request_passes_loop_step(self, collector_with_writer) -> None:
        """loop_step parameter flows through to DB writer data dict."""
        collector, writer = collector_with_writer
        await collector.record_request(
            model="test-model",
            provider="test",
            tier="reason",
            latency_ms=100,
            prompt_tokens=50,
            completion_tokens=25,
            loop_step=3,
        )
        await asyncio.sleep(0.05)
        writer.assert_called_once()
        call_data = writer.call_args[0][1]
        assert call_data["loop_step"] == 3

    @pytest.mark.asyncio
    async def test_record_tool_execution_passes_loop_step(self, collector_with_writer) -> None:
        """loop_step parameter flows through record_tool_execution to DB writer."""
        collector, writer = collector_with_writer
        await collector.record_tool_execution(
            tool_name="analyze_stock",
            latency_ms=200,
            status="ok",
            loop_step=7,
        )
        await asyncio.sleep(0.05)
        writer.assert_called_once()
        call_data = writer.call_args[0][1]
        assert call_data["loop_step"] == 7

    @pytest.mark.asyncio
    async def test_record_request_loop_step_defaults_none(self, collector_with_writer) -> None:
        """loop_step defaults to None when not provided."""
        collector, writer = collector_with_writer
        await collector.record_request(
            model="test-model",
            provider="test",
            tier="reason",
            latency_ms=100,
            prompt_tokens=50,
            completion_tokens=25,
        )
        await asyncio.sleep(0.05)
        writer.assert_called_once()
        call_data = writer.call_args[0][1]
        assert call_data["loop_step"] is None
