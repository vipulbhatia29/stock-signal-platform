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
