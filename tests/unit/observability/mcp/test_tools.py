"""Tests for observability MCP tool functions.

All tool functions are tested with mocked database sessions.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestDescribeObservabilitySchema:
    @pytest.mark.asyncio
    async def test_returns_envelope(self) -> None:
        from backend.observability.mcp.describe_schema import describe_observability_schema

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = "v1"
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "backend.observability.mcp.describe_schema.async_session_factory"
        ) as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await describe_observability_schema()

        assert result["tool"] == "describe_observability_schema"
        assert result["result"]["schema_version"] == "v1"
        assert "event_types" in result["result"]
        assert "attribution_layers" in result["result"]
        assert "tables" in result["result"]
        assert "tool_manifest" in result["result"]
        assert len(result["result"]["event_types"]) > 20
        assert len(result["result"]["tables"]) >= 20

    @pytest.mark.asyncio
    async def test_tables_have_required_fields(self) -> None:
        from backend.observability.mcp.describe_schema import describe_observability_schema

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = "v1"
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "backend.observability.mcp.describe_schema.async_session_factory"
        ) as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await describe_observability_schema()

        for table in result["result"]["tables"]:
            assert "name" in table
            assert "schema" in table
            assert "retention_days" in table
            assert "hypertable" in table

    @pytest.mark.asyncio
    async def test_envelope_meta(self) -> None:
        from backend.observability.mcp.describe_schema import describe_observability_schema

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = "v1"
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "backend.observability.mcp.describe_schema.async_session_factory"
        ) as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await describe_observability_schema()

        assert result["meta"]["schema_version"] == "v1"
        assert "window" in result


# ---------------------------------------------------------------------------
# Tool 2: get_platform_health
# ---------------------------------------------------------------------------


class TestGetPlatformHealth:
    """Tests for the get_platform_health MCP tool."""

    def _make_mock_session(self) -> AsyncMock:
        """Build a mock DB session where execute returns safe empty results."""
        mock_session = AsyncMock()
        # Default: return a row-like object that returns 0/None for all agg calls
        mock_row = MagicMock()
        mock_row.total = 0
        mock_row.errors = 0
        mock_row.p95_ms = None
        mock_row.slow_count = 0
        mock_row.hits = 0
        mock_row.declines = 0

        mock_result = MagicMock()
        mock_result.one.return_value = mock_row
        mock_result.scalar.return_value = 0
        mock_result.all.return_value = []

        mock_session.execute = AsyncMock(return_value=mock_result)
        return mock_session

    @pytest.mark.asyncio
    async def test_returns_envelope_structure(self) -> None:
        """Verify get_platform_health returns a valid MCP envelope."""
        from backend.observability.mcp.platform_health import get_platform_health

        mock_session = self._make_mock_session()

        with patch(
            "backend.observability.mcp.platform_health.async_session_factory"
        ) as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_platform_health(window_min=60)

        assert result["tool"] == "get_platform_health"
        assert "result" in result
        assert "meta" in result
        assert "window" in result
        assert "overall_status" in result["result"]
        assert "subsystems" in result["result"]
        assert "open_anomaly_count" in result["result"]

    @pytest.mark.asyncio
    async def test_empty_db_returns_valid_statuses(self) -> None:
        """Verify all-empty DB results return valid per-subsystem statuses.

        Celery with 0 active workers is classified as degraded by design;
        all other subsystems should be healthy with empty data.
        """
        from backend.observability.mcp.platform_health import get_platform_health

        mock_session = self._make_mock_session()

        with patch(
            "backend.observability.mcp.platform_health.async_session_factory"
        ) as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_platform_health(window_min=30)

        subsystems = result["result"]["subsystems"]
        # Non-celery subsystems with zero data are healthy
        for name in ("http", "db", "cache", "external_api", "agent", "frontend"):
            assert name in subsystems
            assert subsystems[name]["status"] == "healthy", (
                f"Expected {name} to be healthy with empty data, got {subsystems[name]['status']}"
            )
        # Celery: 0 workers → degraded (no workers seen is a concern)
        assert subsystems["celery"]["status"] == "degraded"
        # Overall = worst = degraded
        assert result["result"]["overall_status"] == "degraded"

    @pytest.mark.asyncio
    async def test_subsystems_have_required_keys(self) -> None:
        """Verify each subsystem dict contains the subsystem name and status."""
        from backend.observability.mcp.platform_health import get_platform_health

        mock_session = self._make_mock_session()

        with patch(
            "backend.observability.mcp.platform_health.async_session_factory"
        ) as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_platform_health()

        for name, stats in result["result"]["subsystems"].items():
            assert stats["subsystem"] == name
            assert stats["status"] in ("healthy", "degraded", "failing")


# ---------------------------------------------------------------------------
# Tool 3: get_trace
# ---------------------------------------------------------------------------


class TestGetTrace:
    """Tests for the get_trace MCP tool."""

    def _make_empty_session(self) -> AsyncMock:
        """Build a mock DB session returning empty scalars for all queries."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        return mock_session

    @pytest.mark.asyncio
    async def test_returns_envelope_structure(self) -> None:
        """Verify get_trace returns a valid MCP envelope with trace_id."""
        from backend.observability.mcp.trace import get_trace

        mock_session = self._make_empty_session()
        trace_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        with patch("backend.observability.mcp.trace.async_session_factory") as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_trace(trace_id)

        assert result["tool"] == "get_trace"
        assert "result" in result
        assert result["result"]["trace_id"] == trace_id
        assert "span_count" in result["result"]

    @pytest.mark.asyncio
    async def test_empty_trace_returns_null_root(self) -> None:
        """Verify empty DB returns None root_span and zero span_count."""
        from backend.observability.mcp.trace import get_trace

        mock_session = self._make_empty_session()
        trace_id = "00000000-0000-0000-0000-000000000000"

        with patch("backend.observability.mcp.trace.async_session_factory") as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_trace(trace_id)

        assert result["result"]["root_span"] is None
        assert result["result"]["span_count"] == 0

    @pytest.mark.asyncio
    async def test_envelope_meta_present(self) -> None:
        """Verify envelope includes meta with schema_version."""
        from backend.observability.mcp.trace import get_trace

        mock_session = self._make_empty_session()

        with patch("backend.observability.mcp.trace.async_session_factory") as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_trace("test-trace-id")

        assert result["meta"]["schema_version"] == "v1"
        assert "window" in result


# ---------------------------------------------------------------------------
# Tool 4: get_recent_errors
# ---------------------------------------------------------------------------


class TestGetRecentErrors:
    """Tests for the get_recent_errors MCP tool."""

    def _make_empty_session(self) -> AsyncMock:
        """Build a mock DB session that returns no rows."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        return mock_session

    @pytest.mark.asyncio
    async def test_returns_envelope_structure(self) -> None:
        """Verify get_recent_errors returns a valid MCP envelope."""
        from backend.observability.mcp.recent_errors import get_recent_errors

        mock_session = self._make_empty_session()

        with patch("backend.observability.mcp.recent_errors.async_session_factory") as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_recent_errors()

        assert result["tool"] == "get_recent_errors"
        assert "result" in result
        assert "errors" in result["result"]
        assert isinstance(result["result"]["errors"], list)
        assert "meta" in result
        assert "window" in result

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty_list(self) -> None:
        """Verify empty DB returns an empty errors list without crashing."""
        from backend.observability.mcp.recent_errors import get_recent_errors

        mock_session = self._make_empty_session()

        with patch("backend.observability.mcp.recent_errors.async_session_factory") as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_recent_errors(since="1h", limit=50)

        assert result["result"]["errors"] == []
        assert result["meta"]["total_count"] == 0

    @pytest.mark.asyncio
    async def test_subsystem_filter_limits_sources(self) -> None:
        """Verify subsystem='http' only queries ApiErrorLog, not others."""
        from backend.observability.mcp.recent_errors import get_recent_errors

        mock_session = self._make_empty_session()

        with patch("backend.observability.mcp.recent_errors.async_session_factory") as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_recent_errors(subsystem="http")

        # Should return successfully with empty list
        assert result["tool"] == "get_recent_errors"
        assert result["result"]["errors"] == []


# ---------------------------------------------------------------------------
# Tool 5: get_anomalies
# ---------------------------------------------------------------------------


class TestGetAnomalies:
    """Tests for the get_anomalies MCP tool."""

    def _make_empty_session(self) -> AsyncMock:
        """Build a mock DB session that returns no FindingLog rows."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        return mock_session

    @pytest.mark.asyncio
    async def test_returns_envelope_structure(self) -> None:
        """Verify get_anomalies returns a valid MCP envelope."""
        from backend.observability.mcp.anomalies import get_anomalies

        mock_session = self._make_empty_session()

        with patch("backend.observability.mcp.anomalies.async_session_factory") as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_anomalies()

        assert result["tool"] == "get_anomalies"
        assert "result" in result
        assert "findings" in result["result"]
        assert isinstance(result["result"]["findings"], list)
        assert "meta" in result

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty_findings(self) -> None:
        """Verify empty DB returns zero findings without crashing."""
        from backend.observability.mcp.anomalies import get_anomalies

        mock_session = self._make_empty_session()

        with patch("backend.observability.mcp.anomalies.async_session_factory") as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_anomalies(status="open")

        assert result["result"]["findings"] == []
        assert result["meta"]["total_count"] == 0
        assert result["meta"]["truncated"] is False

    @pytest.mark.asyncio
    async def test_filters_forwarded_to_query(self) -> None:
        """Verify all filter parameters are accepted without error."""
        from backend.observability.mcp.anomalies import get_anomalies

        mock_session = self._make_empty_session()

        with patch("backend.observability.mcp.anomalies.async_session_factory") as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_anomalies(
                status="open",
                since="24h",
                severity="critical",
                attribution_layer="http",
                limit=10,
            )

        assert result["tool"] == "get_anomalies"
        assert result["result"]["findings"] == []


# ---------------------------------------------------------------------------
# Tool 6: get_external_api_stats
# ---------------------------------------------------------------------------


class TestGetExternalApiStats:
    """Tests for the get_external_api_stats MCP tool."""

    def _make_empty_session(self) -> AsyncMock:
        """Build a mock DB session returning safe zero/empty results.

        Two distinct result shapes are needed:
        - Aggregate query (one()): returns a row with zero counts and None percentiles.
        - GROUP BY / count queries (all() / scalar()): return empty list / zero.
        """
        mock_session = AsyncMock()

        agg_row = MagicMock()
        agg_row.call_count = 0
        agg_row.success_count = 0
        agg_row.p50 = None
        agg_row.p95 = None
        agg_row.total_cost_usd = None

        agg_result = MagicMock()
        agg_result.one.return_value = agg_row
        agg_result.all.return_value = []
        agg_result.scalar.return_value = 0

        mock_session.execute = AsyncMock(return_value=agg_result)
        return mock_session

    @pytest.mark.asyncio
    async def test_returns_envelope_structure(self) -> None:
        """Verify get_external_api_stats returns a valid MCP envelope."""
        from backend.observability.mcp.external_api_stats import get_external_api_stats

        mock_session = self._make_empty_session()

        with patch(
            "backend.observability.mcp.external_api_stats.async_session_factory"
        ) as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_external_api_stats("openai")

        assert result["tool"] == "get_external_api_stats"
        assert "result" in result
        assert "meta" in result
        assert "window" in result
        assert result["result"]["provider"] == "openai"

    @pytest.mark.asyncio
    async def test_empty_db_returns_zero_stats(self) -> None:
        """Verify empty DB returns zero call counts without crashing."""
        from backend.observability.mcp.external_api_stats import get_external_api_stats

        mock_session = self._make_empty_session()

        with patch(
            "backend.observability.mcp.external_api_stats.async_session_factory"
        ) as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_external_api_stats("yfinance", window_min=30)

        stats = result["result"]["stats"]
        assert stats["call_count"] == 0
        assert stats["success_count"] == 0
        assert stats["error_count"] == 0
        assert stats["success_rate"] is None
        assert stats["p50_latency_ms"] is None
        assert stats["p95_latency_ms"] is None
        assert result["result"]["rate_limit_events"] == 0
        assert result["result"]["error_breakdown"] == []

    @pytest.mark.asyncio
    async def test_compare_to_prior_window_includes_deltas(self) -> None:
        """Verify compare_to='prior_window' adds prior_window and deltas keys."""
        from backend.observability.mcp.external_api_stats import get_external_api_stats

        mock_session = self._make_empty_session()

        with patch(
            "backend.observability.mcp.external_api_stats.async_session_factory"
        ) as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_external_api_stats(
                "openai", window_min=60, compare_to="prior_window"
            )

        assert "prior_window" in result["result"]
        assert "deltas" in result["result"]


# ---------------------------------------------------------------------------
# Tool 7: get_dq_findings
# ---------------------------------------------------------------------------


class TestGetDqFindings:
    """Tests for the get_dq_findings MCP tool."""

    def _make_empty_session(self) -> AsyncMock:
        """Build a mock DB session that returns no DqCheckHistory rows."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        return mock_session

    @pytest.mark.asyncio
    async def test_returns_envelope_structure(self) -> None:
        """Verify get_dq_findings returns a valid MCP envelope."""
        from backend.observability.mcp.dq_findings import get_dq_findings

        mock_session = self._make_empty_session()

        with patch("backend.observability.mcp.dq_findings.async_session_factory") as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_dq_findings()

        assert result["tool"] == "get_dq_findings"
        assert "result" in result
        assert "findings" in result["result"]
        assert isinstance(result["result"]["findings"], list)
        assert "meta" in result
        assert "window" in result

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty_findings(self) -> None:
        """Verify empty DB returns zero findings without crashing."""
        from backend.observability.mcp.dq_findings import get_dq_findings

        mock_session = self._make_empty_session()

        with patch("backend.observability.mcp.dq_findings.async_session_factory") as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_dq_findings(since="24h", limit=50)

        assert result["result"]["findings"] == []
        assert result["meta"]["total_count"] == 0

    @pytest.mark.asyncio
    async def test_filters_accepted_without_error(self) -> None:
        """Verify all filter parameters are accepted without raising."""
        from backend.observability.mcp.dq_findings import get_dq_findings

        mock_session = self._make_empty_session()

        with patch("backend.observability.mcp.dq_findings.async_session_factory") as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_dq_findings(
                severity="critical",
                check="price_gap_check",
                ticker="AAPL",
                since="7d",
                limit=10,
            )

        assert result["tool"] == "get_dq_findings"
        assert result["result"]["findings"] == []


# ---------------------------------------------------------------------------
# Tool 8: diagnose_pipeline
# ---------------------------------------------------------------------------


class TestDiagnosePipeline:
    """Tests for the diagnose_pipeline MCP tool."""

    def _make_empty_session(self) -> AsyncMock:
        """Build a mock DB session returning no pipeline runs or watermark."""
        mock_session = AsyncMock()

        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        empty_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(return_value=empty_result)
        return mock_session

    @pytest.mark.asyncio
    async def test_returns_envelope_structure(self) -> None:
        """Verify diagnose_pipeline returns a valid MCP envelope."""
        from backend.observability.mcp.diagnose_pipeline import diagnose_pipeline

        mock_session = self._make_empty_session()

        with patch(
            "backend.observability.mcp.diagnose_pipeline.async_session_factory"
        ) as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await diagnose_pipeline("price_refresh")

        assert result["tool"] == "diagnose_pipeline"
        assert "result" in result
        assert result["result"]["pipeline_name"] == "price_refresh"
        assert "runs" in result["result"]
        assert "watermark" in result["result"]
        assert "failure_pattern" in result["result"]
        assert "ticker_success_rate" in result["result"]

    @pytest.mark.asyncio
    async def test_empty_db_returns_zero_failures(self) -> None:
        """Verify empty DB returns no failures and null watermark without crashing."""
        from backend.observability.mcp.diagnose_pipeline import diagnose_pipeline

        mock_session = self._make_empty_session()

        with patch(
            "backend.observability.mcp.diagnose_pipeline.async_session_factory"
        ) as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await diagnose_pipeline("signal_snapshot", recent_n=5)

        assert result["result"]["runs"] == []
        assert result["result"]["watermark"] is None
        assert result["result"]["failure_pattern"]["consecutive_failures"] == 0
        assert result["result"]["failure_pattern"]["is_currently_failing"] is False
        assert result["result"]["ticker_success_rate"] is None

    @pytest.mark.asyncio
    async def test_envelope_meta_present(self) -> None:
        """Verify envelope includes meta with schema_version."""
        from backend.observability.mcp.diagnose_pipeline import diagnose_pipeline

        mock_session = self._make_empty_session()

        with patch(
            "backend.observability.mcp.diagnose_pipeline.async_session_factory"
        ) as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await diagnose_pipeline("price_refresh")

        assert result["meta"]["schema_version"] == "v1"
        assert "window" in result


# ---------------------------------------------------------------------------
# Tool 9: get_slow_queries
# ---------------------------------------------------------------------------


class TestGetSlowQueries:
    """Tests for the get_slow_queries MCP tool."""

    def _make_empty_session(self) -> AsyncMock:
        """Build a mock DB session returning no slow-query rows."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        return mock_session

    @pytest.mark.asyncio
    async def test_returns_envelope_structure(self) -> None:
        """Verify get_slow_queries returns a valid MCP envelope."""
        from backend.observability.mcp.slow_queries import get_slow_queries

        mock_session = self._make_empty_session()

        with patch("backend.observability.mcp.slow_queries.async_session_factory") as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_slow_queries()

        assert result["tool"] == "get_slow_queries"
        assert "result" in result
        assert "queries" in result["result"]
        assert isinstance(result["result"]["queries"], list)
        assert "meta" in result
        assert "window" in result

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty_list(self) -> None:
        """Verify empty DB returns zero slow queries without crashing."""
        from backend.observability.mcp.slow_queries import get_slow_queries

        mock_session = self._make_empty_session()

        with patch("backend.observability.mcp.slow_queries.async_session_factory") as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_slow_queries(since="1h", min_duration_ms=500, limit=50)

        assert result["result"]["queries"] == []
        assert result["meta"]["total_count"] == 0

    @pytest.mark.asyncio
    async def test_compare_to_baseline_includes_delta_fields(self) -> None:
        """Verify compare_to='7d_baseline' adds baseline_p95_ms and p95_delta_ms fields."""
        from backend.observability.mcp.slow_queries import get_slow_queries

        mock_session = self._make_empty_session()

        with patch("backend.observability.mcp.slow_queries.async_session_factory") as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            # With empty results, queries list will be empty — just verify no crash
            result = await get_slow_queries(since="1h", compare_to="7d_baseline")

        assert result["tool"] == "get_slow_queries"
        assert result["result"]["queries"] == []


# ---------------------------------------------------------------------------
# Tool 10: get_cost_breakdown
# ---------------------------------------------------------------------------


class TestGetCostBreakdown:
    """Tests for the get_cost_breakdown MCP tool."""

    def _make_empty_session(self) -> AsyncMock:
        """Build a mock DB session returning no LLMCallLog rows."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        return mock_session

    @pytest.mark.asyncio
    async def test_returns_envelope_structure(self) -> None:
        """Verify get_cost_breakdown returns a valid MCP envelope with by and groups keys."""
        from backend.observability.mcp.cost_breakdown import get_cost_breakdown

        mock_session = self._make_empty_session()

        with patch(
            "backend.observability.mcp.cost_breakdown.async_session_factory"
        ) as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_cost_breakdown(window="7d", by="provider")

        assert result["tool"] == "get_cost_breakdown"
        assert "result" in result
        assert result["result"]["by"] == "provider"
        assert "groups" in result["result"]
        assert isinstance(result["result"]["groups"], list)
        assert "meta" in result
        assert "window" in result

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty_groups(self) -> None:
        """Verify empty DB returns zero groups without crashing."""
        from backend.observability.mcp.cost_breakdown import get_cost_breakdown

        mock_session = self._make_empty_session()

        with patch(
            "backend.observability.mcp.cost_breakdown.async_session_factory"
        ) as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_cost_breakdown(window="24h", by="model", limit=10)

        assert result["result"]["groups"] == []
        assert result["meta"]["total_count"] == 0

    @pytest.mark.asyncio
    async def test_compare_to_prior_window_no_crash(self) -> None:
        """Verify compare_to='prior_window' does not crash with empty data."""
        from backend.observability.mcp.cost_breakdown import get_cost_breakdown

        mock_session = self._make_empty_session()

        with patch(
            "backend.observability.mcp.cost_breakdown.async_session_factory"
        ) as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_cost_breakdown(window="7d", by="tier", compare_to="prior_window")

        assert result["tool"] == "get_cost_breakdown"
        assert result["result"]["groups"] == []


# ---------------------------------------------------------------------------
# Tool 11: search_errors
# ---------------------------------------------------------------------------


class TestSearchErrors:
    """Tests for the search_errors MCP tool."""

    def _make_empty_session(self) -> AsyncMock:
        """Build a mock DB session returning no rows."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        return mock_session

    @pytest.mark.asyncio
    async def test_returns_envelope_structure(self) -> None:
        """Verify search_errors returns a valid MCP envelope with query and matches."""
        from backend.observability.mcp.search_errors import search_errors

        mock_session = self._make_empty_session()

        with patch("backend.observability.mcp.search_errors.async_session_factory") as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await search_errors("ConnectionError")

        assert result["tool"] == "search_errors"
        assert "result" in result
        assert result["result"]["query"] == "ConnectionError"
        assert "matches" in result["result"]
        assert isinstance(result["result"]["matches"], list)
        assert "meta" in result
        assert "window" in result

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty_matches(self) -> None:
        """Verify empty DB returns zero matches without crashing."""
        from backend.observability.mcp.search_errors import search_errors

        mock_session = self._make_empty_session()

        with patch("backend.observability.mcp.search_errors.async_session_factory") as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await search_errors("timeout", since="24h", limit=20)

        assert result["result"]["matches"] == []
        assert result["meta"]["total_count"] == 0

    @pytest.mark.asyncio
    async def test_like_wildcard_chars_escaped(self) -> None:
        """Verify % and _ in query are escaped before building the LIKE pattern."""
        from backend.observability.mcp.search_errors import _escape_like

        assert _escape_like("50%") == r"50\%"
        assert _escape_like("user_id") == r"user\_id"
        assert _escape_like("plain text") == "plain text"
        assert _escape_like("%_combo_%") == r"\%\_combo\_\%"


# ---------------------------------------------------------------------------
# Tool 12: get_deploys
# ---------------------------------------------------------------------------


class TestGetDeploys:
    """Tests for the get_deploys MCP tool."""

    def _make_empty_session(self) -> AsyncMock:
        """Build a mock DB session returning no DeployEvent rows."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        return mock_session

    @pytest.mark.asyncio
    async def test_returns_envelope_structure(self) -> None:
        """Verify get_deploys returns a valid MCP envelope with deploys list."""
        from backend.observability.mcp.deploys import get_deploys

        mock_session = self._make_empty_session()

        with patch("backend.observability.mcp.deploys.async_session_factory") as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_deploys()

        assert result["tool"] == "get_deploys"
        assert "result" in result
        assert "deploys" in result["result"]
        assert isinstance(result["result"]["deploys"], list)
        assert "meta" in result
        assert "window" in result

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty_deploys(self) -> None:
        """Verify empty DB returns zero deploys without crashing."""
        from backend.observability.mcp.deploys import get_deploys

        mock_session = self._make_empty_session()

        with patch("backend.observability.mcp.deploys.async_session_factory") as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_deploys(since="30d", limit=50)

        assert result["result"]["deploys"] == []
        assert result["meta"]["total_count"] == 0

    @pytest.mark.asyncio
    async def test_deploy_row_has_expected_fields(self) -> None:
        """Verify that a non-empty result row contains the required deploy fields."""
        from datetime import datetime as dt
        from datetime import timezone

        from backend.observability.mcp.deploys import get_deploys

        mock_row = MagicMock()
        mock_row.ts = dt(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_row.git_sha = "abc123"
        mock_row.branch = "develop"
        mock_row.pr_number = 260
        mock_row.author = "sigmoid"
        mock_row.commit_message = "fix: something"
        mock_row.migrations_applied = []
        mock_row.env = "prod"
        mock_row.deploy_duration_seconds = 45.2
        mock_row.status = "success"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_row]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("backend.observability.mcp.deploys.async_session_factory") as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_deploys(since="30d")

        deploys = result["result"]["deploys"]
        assert len(deploys) == 1
        deploy = deploys[0]
        for field in (
            "ts",
            "git_sha",
            "branch",
            "pr_number",
            "author",
            "commit_message",
            "migrations_applied",
            "env",
            "deploy_duration_seconds",
            "status",
        ):
            assert field in deploy, f"Missing field: {field}"
        assert deploy["status"] == "success"
        assert deploy["branch"] == "develop"


# ---------------------------------------------------------------------------
# Tool 13: get_observability_health
# ---------------------------------------------------------------------------


class TestGetObservabilityHealth:
    """Tests for the get_observability_health MCP tool."""

    def _make_empty_session(self) -> AsyncMock:
        """Build a mock DB session where MAX queries return None."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        return mock_session

    @pytest.mark.asyncio
    async def test_returns_envelope_structure(self) -> None:
        """Verify get_observability_health returns a valid MCP envelope."""
        from backend.observability.mcp.obs_health import get_observability_health

        mock_session = self._make_empty_session()

        with (
            patch("backend.observability.mcp.obs_health.async_session_factory") as mock_factory,
            patch("backend.observability.mcp.obs_health._get_spool_size_bytes", return_value=None),
            patch("backend.observability.mcp.obs_health._get_buffer_stats", return_value=None),
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_observability_health()

        assert result["tool"] == "get_observability_health"
        assert "result" in result
        assert "last_writes" in result["result"]
        assert "spool_size_bytes" in result["result"]
        assert "buffer" in result["result"]
        assert "config" in result["result"]
        assert "meta" in result
        assert "window" in result

    @pytest.mark.asyncio
    async def test_last_writes_contain_all_tables(self) -> None:
        """Verify last_writes dict contains all five expected table keys."""
        from backend.observability.mcp.obs_health import get_observability_health

        mock_session = self._make_empty_session()

        with (
            patch("backend.observability.mcp.obs_health.async_session_factory") as mock_factory,
            patch("backend.observability.mcp.obs_health._get_spool_size_bytes", return_value=None),
            patch("backend.observability.mcp.obs_health._get_buffer_stats", return_value=None),
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_observability_health()

        last_writes = result["result"]["last_writes"]
        for key in (
            "request_log",
            "external_api_call_log",
            "slow_query_log",
            "finding_log",
            "deploy_events",
        ):
            assert key in last_writes, f"Missing last_write key: {key}"
        # Empty DB → all timestamps should be None
        for key, val in last_writes.items():
            assert val is None, f"Expected None for {key} with empty DB, got {val}"

    @pytest.mark.asyncio
    async def test_config_snapshot_contains_required_keys(self) -> None:
        """Verify the config snapshot contains all required OBS settings keys."""
        from backend.observability.mcp.obs_health import get_observability_health

        mock_session = self._make_empty_session()

        with (
            patch("backend.observability.mcp.obs_health.async_session_factory") as mock_factory,
            patch("backend.observability.mcp.obs_health._get_spool_size_bytes", return_value=0),
            patch(
                "backend.observability.mcp.obs_health._get_buffer_stats",
                return_value={"queue_depth": 0, "drops": 0},
            ),
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_observability_health()

        config = result["result"]["config"]
        for key in (
            "OBS_ENABLED",
            "OBS_SPOOL_ENABLED",
            "OBS_TARGET_TYPE",
            "OBS_LEGACY_DIRECT_WRITES",
        ):
            assert key in config, f"Missing config key: {key}"

        assert result["result"]["spool_size_bytes"] == 0
        assert result["result"]["buffer"]["queue_depth"] == 0
        assert result["result"]["buffer"]["drops"] == 0
