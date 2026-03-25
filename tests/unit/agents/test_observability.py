"""Tests for ObservabilityCollector in-memory metrics."""

import pytest

from backend.agents.observability import ObservabilityCollector


class TestRecordRequest:
    """Tests for recording successful LLM requests."""

    @pytest.mark.asyncio
    async def test_record_increments_model_count(self) -> None:
        """Recording a request should increment the per-model count."""
        collector = ObservabilityCollector()
        await collector.record_request(
            model="llama-3.3-70b",
            provider="groq",
            tier="planner",
            latency_ms=150,
            prompt_tokens=100,
            completion_tokens=50,
        )
        stats = collector.get_stats()
        assert stats["requests_by_model"]["llama-3.3-70b"] == 1

    @pytest.mark.asyncio
    async def test_record_updates_rpm(self) -> None:
        """Recording a request should update RPM tracking."""
        collector = ObservabilityCollector()
        await collector.record_request(
            model="llama-3.3-70b",
            provider="groq",
            tier="planner",
            latency_ms=150,
            prompt_tokens=100,
            completion_tokens=50,
        )
        stats = collector.get_stats()
        assert stats["rpm_by_model"]["llama-3.3-70b"] == 1

    @pytest.mark.asyncio
    async def test_record_tracks_latency(self) -> None:
        """Recording a request should track latency."""
        collector = ObservabilityCollector()
        await collector.record_request(
            model="llama-3.3-70b",
            provider="groq",
            tier="planner",
            latency_ms=200,
            prompt_tokens=100,
            completion_tokens=50,
        )
        health = collector.get_tier_health()
        entry = next(t for t in health["tiers"] if t["model"] == "llama-3.3-70b")
        assert entry["latency"]["avg_ms"] == 200

    @pytest.mark.asyncio
    async def test_multiple_requests_accumulate(self) -> None:
        """Multiple requests should accumulate correctly."""
        collector = ObservabilityCollector()
        for _ in range(3):
            await collector.record_request(
                model="llama-3.3-70b",
                provider="groq",
                tier="planner",
                latency_ms=100,
                prompt_tokens=50,
                completion_tokens=25,
            )
        stats = collector.get_stats()
        assert stats["requests_by_model"]["llama-3.3-70b"] == 3
        assert stats["rpm_by_model"]["llama-3.3-70b"] == 3


class TestRecordCascade:
    """Tests for recording cascade events."""

    @pytest.mark.asyncio
    async def test_cascade_increments_count(self) -> None:
        """Recording a cascade should increment the cascade count."""
        collector = ObservabilityCollector()
        await collector.record_cascade(
            from_model="llama-3.3-70b",
            reason="rate_limit",
            provider="groq",
            tier="planner",
        )
        stats = collector.get_stats()
        assert stats["cascade_count"] == 1

    @pytest.mark.asyncio
    async def test_cascade_tracks_per_model(self) -> None:
        """Cascade events should be tracked per model."""
        collector = ObservabilityCollector()
        await collector.record_cascade(
            from_model="llama-3.3-70b",
            reason="rate_limit",
            provider="groq",
            tier="planner",
        )
        stats = collector.get_stats()
        assert stats["cascades_by_model"]["llama-3.3-70b"] == 1

    @pytest.mark.asyncio
    async def test_cascade_recorded_in_log(self) -> None:
        """Cascade events should appear in the cascade log."""
        collector = ObservabilityCollector()
        await collector.record_cascade(
            from_model="llama-3.3-70b",
            reason="rate_limit",
            provider="groq",
            tier="planner",
        )
        stats = collector.get_stats()
        assert len(stats["cascade_log"]) == 1
        assert stats["cascade_log"][0]["model"] == "llama-3.3-70b"
        assert stats["cascade_log"][0]["reason"] == "rate_limit"


class TestTierHealth:
    """Tests for tier health classification."""

    @pytest.mark.asyncio
    async def test_healthy_no_failures(self) -> None:
        """A model with no recent failures should be 'healthy'."""
        collector = ObservabilityCollector()
        await collector.record_request(
            model="llama-3.3-70b",
            provider="groq",
            tier="planner",
            latency_ms=100,
            prompt_tokens=50,
            completion_tokens=25,
        )
        health = collector.get_tier_health()
        entry = next(t for t in health["tiers"] if t["model"] == "llama-3.3-70b")
        assert entry["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_degraded_few_failures(self) -> None:
        """A model with 1-3 recent failures should be 'degraded'."""
        collector = ObservabilityCollector()
        for _ in range(2):
            await collector.record_cascade(
                from_model="llama-3.3-70b",
                reason="rate_limit",
                provider="groq",
                tier="planner",
            )
        health = collector.get_tier_health()
        entry = next(t for t in health["tiers"] if t["model"] == "llama-3.3-70b")
        assert entry["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_down_many_failures(self) -> None:
        """A model with 4+ recent failures should be 'down'."""
        collector = ObservabilityCollector()
        for _ in range(5):
            await collector.record_cascade(
                from_model="llama-3.3-70b",
                reason="rate_limit",
                provider="groq",
                tier="planner",
            )
        health = collector.get_tier_health()
        entry = next(t for t in health["tiers"] if t["model"] == "llama-3.3-70b")
        assert entry["status"] == "down"

    @pytest.mark.asyncio
    async def test_disabled_status(self) -> None:
        """A manually disabled model should show 'disabled'."""
        collector = ObservabilityCollector()
        collector.toggle_model("llama-3.3-70b", enabled=False)
        health = collector.get_tier_health()
        entry = next(t for t in health["tiers"] if t["model"] == "llama-3.3-70b")
        assert entry["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_health_summary_counts(self) -> None:
        """Health summary should count models by status."""
        collector = ObservabilityCollector()
        await collector.record_request(
            model="model-a",
            provider="groq",
            tier="planner",
            latency_ms=100,
            prompt_tokens=50,
            completion_tokens=25,
        )
        collector.toggle_model("model-b", enabled=False)
        health = collector.get_tier_health()
        assert health["summary"]["total"] == 2
        assert health["summary"]["healthy"] == 1
        assert health["summary"]["disabled"] == 1


class TestToggleModel:
    """Tests for model enable/disable."""

    def test_toggle_disable(self) -> None:
        """Disabling a model should add it to disabled set."""
        collector = ObservabilityCollector()
        collector.toggle_model("llama-3.3-70b", enabled=False)
        assert "llama-3.3-70b" in collector._disabled_models

    def test_toggle_enable(self) -> None:
        """Re-enabling a model should remove it from disabled set."""
        collector = ObservabilityCollector()
        collector.toggle_model("llama-3.3-70b", enabled=False)
        collector.toggle_model("llama-3.3-70b", enabled=True)
        assert "llama-3.3-70b" not in collector._disabled_models
