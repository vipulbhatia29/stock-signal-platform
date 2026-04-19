"""Tests for AnomalyRule base types and engine orchestrator."""

import asyncio

import pytest

from backend.observability.anomaly.base import AnomalyRule, Finding
from backend.observability.anomaly.engine import run_anomaly_scan


class TestFindingDataclass:
    def test_finding_requires_mandatory_fields(self) -> None:
        f = Finding(
            kind="test_rule",
            attribution_layer="test",
            severity="warning",
            title="Test finding",
            evidence={"count": 42},
            dedup_key="test_rule:test:entity1",
        )
        assert f.kind == "test_rule"
        assert f.severity == "warning"
        assert f.related_traces == []
        assert f.suggested_jira_fields is None

    def test_finding_is_frozen(self) -> None:
        f = Finding(
            kind="test",
            attribution_layer="test",
            severity="info",
            title="t",
            evidence={},
            dedup_key="k",
        )
        try:
            f.kind = "changed"  # type: ignore[misc]
            assert False, "Should raise"
        except AttributeError:
            pass

    def test_anomaly_rule_is_abstract(self) -> None:
        try:
            AnomalyRule()  # type: ignore[abstract]
            assert False, "Should raise"
        except TypeError:
            pass


class _PassRule(AnomalyRule):
    @property
    def name(self) -> str:
        return "pass_rule"

    async def evaluate(self) -> list[Finding]:
        return [
            Finding(
                kind="pass_rule",
                attribution_layer="test",
                severity="info",
                title="Found something",
                evidence={"x": 1},
                dedup_key="pass_rule:test:x",
            )
        ]


class _FailRule(AnomalyRule):
    @property
    def name(self) -> str:
        return "fail_rule"

    async def evaluate(self) -> list[Finding]:
        raise RuntimeError("rule crashed")


class _SlowRule(AnomalyRule):
    @property
    def name(self) -> str:
        return "slow_rule"

    async def evaluate(self) -> list[Finding]:
        await asyncio.sleep(60)
        return []


class TestRunAnomalyScan:
    @pytest.mark.asyncio
    async def test_collects_findings_from_passing_rules(self) -> None:
        findings = await run_anomaly_scan(rules=[_PassRule()], semaphore_limit=2, rule_timeout_s=5)
        assert len(findings) == 1
        assert findings[0].kind == "pass_rule"

    @pytest.mark.asyncio
    async def test_failing_rule_does_not_block_others(self) -> None:
        findings = await run_anomaly_scan(
            rules=[_FailRule(), _PassRule()], semaphore_limit=2, rule_timeout_s=5
        )
        assert len(findings) == 1
        assert findings[0].kind == "pass_rule"

    @pytest.mark.asyncio
    async def test_slow_rule_times_out_without_blocking(self) -> None:
        findings = await run_anomaly_scan(
            rules=[_SlowRule(), _PassRule()], semaphore_limit=2, rule_timeout_s=0.1
        )
        assert len(findings) == 1
        assert findings[0].kind == "pass_rule"

    @pytest.mark.asyncio
    async def test_empty_rules_returns_empty(self) -> None:
        findings = await run_anomaly_scan(rules=[], semaphore_limit=2, rule_timeout_s=5)
        assert findings == []
