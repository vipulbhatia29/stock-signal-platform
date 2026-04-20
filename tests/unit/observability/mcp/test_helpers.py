"""Tests for MCP tool shared helpers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.observability.mcp._helpers import build_envelope, clamp_limit, parse_since


class TestParseSince:
    def test_hours(self) -> None:
        now = datetime.now(timezone.utc)
        cutoff = parse_since("1h")
        assert (now - cutoff) < timedelta(hours=1, seconds=5)

    def test_days(self) -> None:
        now = datetime.now(timezone.utc)
        cutoff = parse_since("7d")
        assert (now - cutoff) < timedelta(days=7, seconds=5)

    def test_minutes(self) -> None:
        now = datetime.now(timezone.utc)
        cutoff = parse_since("30m")
        assert (now - cutoff) < timedelta(minutes=30, seconds=5)

    def test_invalid_falls_back(self) -> None:
        cutoff = parse_since("bogus", default="24h")
        now = datetime.now(timezone.utc)
        assert (now - cutoff) < timedelta(hours=24, seconds=5)

    def test_none_uses_default(self) -> None:
        cutoff = parse_since(None, default="1h")
        now = datetime.now(timezone.utc)
        assert (now - cutoff) < timedelta(hours=1, seconds=5)


class TestClampLimit:
    def test_default(self) -> None:
        assert clamp_limit(None) == 50

    def test_max(self) -> None:
        assert clamp_limit(1000) == 500

    def test_min(self) -> None:
        assert clamp_limit(0) == 1

    def test_normal(self) -> None:
        assert clamp_limit(25) == 25


class TestBuildEnvelope:
    def test_structure(self) -> None:
        result = build_envelope("get_anomalies", {"items": []}, total_count=0)
        assert result["tool"] == "get_anomalies"
        assert "window" in result
        assert result["result"] == {"items": []}
        assert result["meta"]["total_count"] == 0
        assert result["meta"]["schema_version"] == "v1"

    def test_truncated_flag(self) -> None:
        result = build_envelope("t", {}, total_count=100, limit=50)
        assert result["meta"]["truncated"] is True

    def test_not_truncated(self) -> None:
        result = build_envelope("t", {}, total_count=10, limit=50)
        assert result["meta"]["truncated"] is False
