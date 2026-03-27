"""Unit tests for tool_groups — intent-based tool schema resolution."""

from __future__ import annotations

from unittest.mock import MagicMock

from backend.agents.tool_groups import TOOL_GROUPS, get_tool_schemas_for_group
from backend.tools.base import ToolInfo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_schema(name: str) -> dict:
    """Return a minimal OpenAI function-calling schema dict for a tool name."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"Description for {name}",
            "parameters": {"type": "object", "properties": {}},
        },
    }


def _make_registry(tool_names: list[str]) -> MagicMock:
    """Build a mock ToolRegistry for the given tool names.

    Args:
        tool_names: List of tool names to populate the mock registry with.

    Returns:
        A MagicMock that behaves like a ToolRegistry.
    """
    registry = MagicMock()

    def _get(name: str):
        if name not in tool_names:
            raise KeyError(name)
        tool = MagicMock()
        tool.info.return_value = ToolInfo(
            name=name,
            description=f"Description for {name}",
            category="test",
            parameters={"type": "object", "properties": {}},
        )
        return tool

    registry.get.side_effect = _get
    registry.discover.return_value = [
        ToolInfo(
            name=n,
            description=f"Description for {n}",
            category="test",
            parameters={"type": "object", "properties": {}},
        )
        for n in tool_names
    ]
    return registry


# All tool names used by TOOL_GROUPS (excluding None entries)
_ALL_GROUP_TOOL_NAMES: list[str] = sorted(
    {name for names in TOOL_GROUPS.values() if names is not None for name in names}
)

_FULL_REGISTRY = _make_registry(_ALL_GROUP_TOOL_NAMES)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStockGroup:
    """Tests for the 'stock' tool group."""

    def test_stock_group_returns_8_schemas(self) -> None:
        """stock group has 8 tools and every schema has type='function'."""
        registry = _make_registry(TOOL_GROUPS["stock"])  # type: ignore[arg-type]
        schemas = get_tool_schemas_for_group("stock", registry)

        assert len(schemas) == 8
        for schema in schemas:
            assert schema["type"] == "function"
            assert "function" in schema


class TestPortfolioGroup:
    """Tests for the 'portfolio' tool group."""

    def test_portfolio_group_includes_analyze_stock(self) -> None:
        """portfolio group includes analyze_stock for holding drill-downs."""
        registry = _make_registry(TOOL_GROUPS["portfolio"])  # type: ignore[arg-type]
        schemas = get_tool_schemas_for_group("portfolio", registry)

        names = [s["function"]["name"] for s in schemas]
        assert "analyze_stock" in names


class TestGeneralGroup:
    """Tests for the None / 'general' group fallback."""

    def test_general_key_returns_all_tools(self) -> None:
        """'general' group key → all tools from registry.discover()."""
        all_names = ["tool_a", "tool_b", "tool_c"]
        registry = _make_registry(all_names)
        schemas = get_tool_schemas_for_group("general", registry)

        assert len(schemas) == len(all_names)
        registry.discover.assert_called_once()

    def test_none_group_returns_all_tools(self) -> None:
        """None group argument → all tools from registry.discover()."""
        all_names = ["tool_a", "tool_b", "tool_c"]
        registry = _make_registry(all_names)
        schemas = get_tool_schemas_for_group(None, registry)

        assert len(schemas) == len(all_names)
        registry.discover.assert_called_once()


class TestUnknownGroup:
    """Tests for unknown / unrecognised group keys."""

    def test_unknown_group_returns_all_tools(self) -> None:
        """Unrecognised group key falls back to all tools from registry."""
        all_names = ["tool_a", "tool_b"]
        registry = _make_registry(all_names)
        schemas = get_tool_schemas_for_group("completely_unknown_group", registry)

        assert len(schemas) == len(all_names)
        registry.discover.assert_called_once()


class TestMissingToolName:
    """Tests for graceful handling of tool names not in the registry."""

    def test_missing_tool_name_skipped_no_crash(self) -> None:
        """Tool name absent from registry is silently skipped; no exception."""
        # Only register one of the two names in a two-name group
        partial_registry = _make_registry(["analyze_stock"])

        # Build a fake group with one valid + one missing name
        from unittest.mock import patch

        fake_groups = {
            "fake_group": ["analyze_stock", "nonexistent_tool"],
        }
        with patch("backend.agents.tool_groups.TOOL_GROUPS", fake_groups):
            schemas = get_tool_schemas_for_group("fake_group", partial_registry)

        # Only the valid tool schema is returned
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "analyze_stock"


class TestToolGroupNamesValid:
    """Validate that all tool names in TOOL_GROUPS exist as internal tools."""

    def test_tool_group_names_match_internal_tool_classes(self) -> None:
        """Every tool name in TOOL_GROUPS must be in INTERNAL_TOOL_CLASSES.name.

        Uses INTERNAL_TOOL_CLASSES directly (no DB / env needed) to verify the
        group definitions stay in sync with the real tool catalogue.
        """
        from backend.tools.build_registry import INTERNAL_TOOL_CLASSES

        # Instantiate each class to read its .name attribute
        internal_names = {cls().name for cls in INTERNAL_TOOL_CLASSES}

        all_group_names = {
            name for names in TOOL_GROUPS.values() if names is not None for name in names
        }

        unknown = all_group_names - internal_names
        assert not unknown, (
            f"Tool names in TOOL_GROUPS not found in INTERNAL_TOOL_CLASSES: {unknown}"
        )
