"""Tests for the CLI health_report script."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from scripts.health_report import (
    _build_parser,
    _extract_providers,
    _fmt_anomalies,
    _fmt_full_report,
    _fmt_layer_report,
    _fmt_trace,
    _since_to_minutes,
)

# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------

_HEALTH_ENVELOPE = {
    "tool": "get_platform_health",
    "window": {"from": "2026-04-20T09:00:00Z", "to": "2026-04-20T10:00:00Z"},
    "result": {
        "overall_status": "healthy",
        "subsystems": {
            "http": {"status": "healthy", "total_requests": 100, "error_count": 2},
            "external_api": {
                "status": "healthy",
                "providers": {
                    "yfinance": {"total_calls": 50, "error_count": 1},
                    "openai": {"total_calls": 30, "error_count": 0},
                },
            },
            "celery": {
                "status": "healthy",
                "recent_pipelines": [
                    {"pipeline_name": "nightly_price_refresh", "status": "success"},
                    {"pipeline_name": "news_ingest", "status": "success"},
                ],
            },
        },
    },
    "meta": {"total_count": 0, "truncated": False, "schema_version": "v1"},
}

_ANOMALIES_ENVELOPE = {
    "tool": "get_anomalies",
    "window": {"from": "2026-04-20T09:00:00Z", "to": "2026-04-20T10:00:00Z"},
    "result": {
        "findings": [
            {
                "id": "f-1",
                "kind": "external_api_error_rate_elevated",
                "attribution_layer": "external_api",
                "severity": "warning",
                "status": "open",
                "title": "yfinance 429 rate elevated",
                "evidence": {"provider": "yfinance", "error_count_1h": 47},
                "remediation_hint": "Check yfinance rate-limiter state in Redis.",
            },
        ],
    },
    "meta": {"total_count": 1, "truncated": False, "schema_version": "v1"},
}

_ERRORS_ENVELOPE = {
    "tool": "get_recent_errors",
    "window": {"from": "2026-04-20T09:00:00Z", "to": "2026-04-20T10:00:00Z"},
    "result": {
        "errors": [
            {"source": "http", "severity": "warning", "message": "401 Unauthorized"},
            {"source": "http", "severity": "warning", "message": "401 Unauthorized"},
            {"source": "external_api", "severity": "error", "message": "429 Too Many Requests"},
        ],
    },
    "meta": {"total_count": 3, "truncated": False, "schema_version": "v1"},
}

_TRACE_ENVELOPE = {
    "tool": "get_trace",
    "window": {"from": "2026-04-20T09:00:00Z", "to": "2026-04-20T10:00:00Z"},
    "result": {
        "trace_id": "abc-123",
        "root_span": {
            "kind": "http",
            "path": "/api/v1/stocks",
            "status_code": 200,
            "latency_ms": 450,
            "children": [
                {"kind": "db.query", "duration_ms": 120, "children": []},
                {"kind": "cache.get", "duration_ms": 2, "children": []},
            ],
        },
    },
    "meta": {"total_count": 0, "truncated": False, "schema_version": "v1"},
}


# ---------------------------------------------------------------------------
# Unit tests — _since_to_minutes
# ---------------------------------------------------------------------------


class TestSinceToMinutes:
    def test_minutes(self) -> None:
        assert _since_to_minutes("30m") == 30

    def test_hours(self) -> None:
        assert _since_to_minutes("1h") == 60

    def test_days(self) -> None:
        assert _since_to_minutes("7d") == 7 * 1440

    def test_24h(self) -> None:
        assert _since_to_minutes("24h") == 1440

    def test_invalid_fallback(self) -> None:
        assert _since_to_minutes("bogus") == 60


# ---------------------------------------------------------------------------
# Unit tests — _extract_providers
# ---------------------------------------------------------------------------


class TestExtractProviders:
    def test_extracts_provider_names(self) -> None:
        providers = _extract_providers(_HEALTH_ENVELOPE)
        assert sorted(providers) == ["openai", "yfinance"]

    def test_empty_when_no_providers(self) -> None:
        assert _extract_providers({"result": {}}) == []


# ---------------------------------------------------------------------------
# Unit tests — Markdown formatters
# ---------------------------------------------------------------------------


class TestFmtFullReport:
    def test_contains_status_header(self) -> None:
        data = {
            "health": _HEALTH_ENVELOPE,
            "anomalies": _ANOMALIES_ENVELOPE,
            "errors": _ERRORS_ENVELOPE,
            "external_stats": {},
        }
        md = _fmt_full_report(data, "1h")
        assert "# Platform Health" in md
        assert "GREEN" in md or "healthy" in md.lower()

    def test_contains_anomaly_section(self) -> None:
        data = {
            "health": _HEALTH_ENVELOPE,
            "anomalies": _ANOMALIES_ENVELOPE,
            "errors": _ERRORS_ENVELOPE,
            "external_stats": {},
        }
        md = _fmt_full_report(data, "1h")
        assert "Open Anomalies (1)" in md
        assert "yfinance 429 rate elevated" in md

    def test_contains_error_summary(self) -> None:
        data = {
            "health": _HEALTH_ENVELOPE,
            "anomalies": _ANOMALIES_ENVELOPE,
            "errors": _ERRORS_ENVELOPE,
            "external_stats": {},
        }
        md = _fmt_full_report(data, "1h")
        assert "Recent Errors" in md
        assert "http: 2 rows" in md

    def test_no_anomalies_message(self) -> None:
        empty_anomalies = {
            "result": {"findings": []},
            "meta": {"total_count": 0},
        }
        data = {
            "health": _HEALTH_ENVELOPE,
            "anomalies": empty_anomalies,
            "errors": _ERRORS_ENVELOPE,
            "external_stats": {},
        }
        md = _fmt_full_report(data, "1h")
        assert "No open anomalies" in md

    def test_external_api_table(self) -> None:
        data = {
            "health": _HEALTH_ENVELOPE,
            "anomalies": _ANOMALIES_ENVELOPE,
            "errors": _ERRORS_ENVELOPE,
            "external_stats": {
                "yfinance": {
                    "current_window": {
                        "total_calls": 1240,
                        "success_rate": 0.962,
                        "p95_latency_ms": 450,
                        "error_count": 47,
                        "total_cost_usd": 0.0,
                    },
                },
            },
        }
        md = _fmt_full_report(data, "24h")
        assert "| yfinance |" in md
        assert "96.2%" in md


class TestFmtAnomalies:
    def test_renders_findings(self) -> None:
        md = _fmt_anomalies(_ANOMALIES_ENVELOPE)
        assert "Open Anomalies (1)" in md
        assert "yfinance 429 rate elevated" in md
        assert "Hint:" in md

    def test_empty_findings(self) -> None:
        empty = {"result": {"findings": []}}
        md = _fmt_anomalies(empty)
        assert "No open anomalies" in md


class TestFmtTrace:
    def test_renders_span_tree(self) -> None:
        md = _fmt_trace(_TRACE_ENVELOPE)
        assert "Trace: abc-123" in md
        assert "[http]" in md
        assert "[db.query]" in md
        assert "120ms" in md

    def test_no_spans(self) -> None:
        empty = {"result": {"trace_id": "x", "spans": []}}
        md = _fmt_trace(empty)
        assert "No spans found" in md

    def test_flat_spans_fallback(self) -> None:
        flat = {
            "result": {
                "trace_id": "x",
                "spans": [
                    {"kind": "http", "latency_ms": 100, "detail": "GET /api"},
                ],
            },
        }
        md = _fmt_trace(flat)
        assert "1 spans" in md


class TestFmtLayerReport:
    def test_renders_errors(self) -> None:
        data = {
            "layer": "http",
            "errors": {
                "result": {
                    "errors": [
                        {
                            "severity": "warning",
                            "timestamp": "2026-04-20T10:00:00Z",
                            "message": "401 Unauthorized",
                        },
                    ],
                },
                "meta": {"total_count": 1},
            },
        }
        md = _fmt_layer_report(data, "1h")
        assert "Layer Report: http" in md
        assert "Errors (1)" in md


# ---------------------------------------------------------------------------
# Unit tests — argument parser
# ---------------------------------------------------------------------------


class TestParser:
    def test_defaults(self) -> None:
        parser = _build_parser()
        args = parser.parse_args([])
        assert args.since == "1h"
        assert args.layer is None
        assert args.provider is None
        assert args.trace is None
        assert not args.anomalies
        assert not args.json_output

    def test_all_flags(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["--since=24h", "--anomalies", "--json"])
        assert args.since == "24h"
        assert args.anomalies
        assert args.json_output

    def test_layer_provider(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["--layer=external_api", "--provider=yfinance"])
        assert args.layer == "external_api"
        assert args.provider == "yfinance"

    def test_trace_flag(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["--trace=abc-123"])
        assert args.trace == "abc-123"


# ---------------------------------------------------------------------------
# Integration-style tests — async data fetching (mocked)
# ---------------------------------------------------------------------------


class TestAsyncMain:
    @pytest.mark.asyncio
    async def test_full_report(self, capsys: pytest.CaptureFixture[str]) -> None:
        from scripts.health_report import _async_main

        with (
            patch(
                "backend.observability.mcp.platform_health.get_platform_health",
                new_callable=AsyncMock,
                return_value=_HEALTH_ENVELOPE,
            ) as mock_health,
            patch(
                "backend.observability.mcp.anomalies.get_anomalies",
                new_callable=AsyncMock,
                return_value=_ANOMALIES_ENVELOPE,
            ),
            patch(
                "backend.observability.mcp.recent_errors.get_recent_errors",
                new_callable=AsyncMock,
                return_value=_ERRORS_ENVELOPE,
            ),
            patch(
                "backend.observability.mcp.external_api_stats.get_external_api_stats",
                new_callable=AsyncMock,
                return_value={"result": {"current_window": {}}},
            ),
        ):
            parser = _build_parser()
            args = parser.parse_args(["--since=1h"])
            await _async_main(args)
            captured = capsys.readouterr()
            assert "Platform Health" in captured.out
            mock_health.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_json_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        from scripts.health_report import _async_main

        with (
            patch(
                "backend.observability.mcp.anomalies.get_anomalies",
                new_callable=AsyncMock,
                return_value=_ANOMALIES_ENVELOPE,
            ),
        ):
            parser = _build_parser()
            args = parser.parse_args(["--anomalies", "--json"])
            await _async_main(args)
            captured = capsys.readouterr()
            parsed = json.loads(captured.out)
            assert "result" in parsed

    @pytest.mark.asyncio
    async def test_trace_mode(self, capsys: pytest.CaptureFixture[str]) -> None:
        from scripts.health_report import _async_main

        with patch(
            "backend.observability.mcp.trace.get_trace",
            new_callable=AsyncMock,
            return_value=_TRACE_ENVELOPE,
        ):
            parser = _build_parser()
            args = parser.parse_args(["--trace=abc-123"])
            await _async_main(args)
            captured = capsys.readouterr()
            assert "abc-123" in captured.out
