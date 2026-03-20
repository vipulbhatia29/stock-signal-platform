"""Tests for ToolRegistry."""

import pytest
from pydantic import BaseModel, Field

from backend.tools.base import BaseTool, ToolFilter, ToolResult
from backend.tools.registry import ToolRegistry


class FakeTool(BaseTool):
    """A fake tool for testing."""

    def __init__(self, name: str = "fake_tool", category: str = "test"):
        self.name = name
        self.description = f"Fake tool: {name}"
        self.category = category
        self.parameters = {"type": "object", "properties": {}}
        self.cache_policy = None
        self.timeout_seconds = 5.0

    async def execute(self, params):
        """Return a successful result."""
        return ToolResult(status="ok", data={"result": "success"})


class FakeInput(BaseModel):
    """Input schema for fake_typed tool."""

    ticker: str = Field(description="Stock ticker symbol")
    limit: int = Field(default=10, description="Max results")


class FakeTypedTool(BaseTool):
    """A fake tool with explicit args_schema."""

    name = "fake_typed"
    description = "Fake tool with Pydantic schema"
    category = "test"
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Stock ticker symbol"},
            "limit": {"type": "integer", "description": "Max results", "default": 10},
        },
        "required": ["ticker"],
    }
    args_schema = FakeInput
    timeout_seconds = 5.0

    async def execute(self, params):
        """Return params as data."""
        return ToolResult(status="ok", data=params)


@pytest.fixture
def registry():
    """Fresh ToolRegistry for each test."""
    return ToolRegistry()


def test_register_and_get(registry):
    """Register a tool and retrieve it by name."""
    tool = FakeTool()
    registry.register(tool)
    assert registry.get("fake_tool") is tool


def test_register_duplicate_raises(registry):
    """Registering a tool with the same name raises ValueError."""
    tool = FakeTool()
    registry.register(tool)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(tool)


def test_get_unknown_raises(registry):
    """Getting an unknown tool raises KeyError."""
    with pytest.raises(KeyError):
        registry.get("nonexistent")


def test_discover_returns_all(registry):
    """discover() returns metadata for all registered tools."""
    registry.register(FakeTool("tool_a", "analysis"))
    registry.register(FakeTool("tool_b", "data"))
    infos = registry.discover()
    assert len(infos) == 2
    assert {i.name for i in infos} == {"tool_a", "tool_b"}


def test_by_category(registry):
    """by_category() filters tools by category."""
    registry.register(FakeTool("tool_a", "analysis"))
    registry.register(FakeTool("tool_b", "data"))
    registry.register(FakeTool("tool_c", "analysis"))
    result = registry.by_category("analysis")
    assert len(result) == 2


def test_schemas_with_filter(registry):
    """schemas() returns LLM-compatible schemas for filtered tools."""
    registry.register(FakeTool("tool_a", "analysis"))
    registry.register(FakeTool("tool_b", "data"))
    f = ToolFilter(categories=["analysis"])
    schemas = registry.schemas(f)
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "tool_a"


@pytest.mark.asyncio
async def test_execute(registry):
    """execute() runs a tool and returns its result."""
    tool = FakeTool()
    registry.register(tool)
    result = await registry.execute("fake_tool", {})
    assert result.status == "ok"


def test_health_all_ok(registry):
    """health() returns True for all registered tools."""
    registry.register(FakeTool("t1"))
    health = registry.health()
    assert health["t1"] is True


def test_register_mcp(registry):
    """register_mcp() registers all tools from an adapter."""
    from unittest.mock import MagicMock

    adapter = MagicMock()
    tool_a = FakeTool("mcp_tool_a", "sec")
    tool_b = FakeTool("mcp_tool_b", "sec")
    adapter.get_tools.return_value = [tool_a, tool_b]

    registry.register_mcp(adapter)
    assert registry.get("mcp_tool_a") is tool_a
    assert registry.get("mcp_tool_b") is tool_b
    assert len(registry.discover()) == 2


# ─── args_schema tests (KAN-60) ───────────────────────────────────────────


def test_get_langchain_tools_uses_explicit_args_schema(registry):
    """get_langchain_tools() passes args_schema to StructuredTool when available."""
    tool = FakeTypedTool()
    registry.register(tool)
    lc_tools = registry.get_langchain_tools(ToolFilter(categories=["test"]))
    assert len(lc_tools) == 1
    lc_tool = lc_tools[0]
    assert lc_tool.name == "fake_typed"
    # Verify the schema has the correct fields, not a single 'kwargs' blob
    schema = lc_tool.args_schema.model_json_schema()
    assert "ticker" in schema["properties"]
    assert "limit" in schema["properties"]
    assert "kwargs" not in schema["properties"]


@pytest.mark.asyncio
async def test_langchain_tool_wrapper_passes_kwargs_directly(registry):
    """Wrapper passes validated kwargs directly to execute() — no double-wrapping."""
    tool = FakeTypedTool()
    registry.register(tool)
    lc_tools = registry.get_langchain_tools(ToolFilter(categories=["test"]))
    lc_tool = lc_tools[0]
    result = await lc_tool.ainvoke({"ticker": "AAPL", "limit": 5})
    import json

    data = json.loads(result)
    assert data["ticker"] == "AAPL"
    assert data["limit"] == 5


@pytest.mark.asyncio
async def test_langchain_tool_wrapper_uses_defaults(registry):
    """Wrapper lets Pydantic defaults fill in optional params."""
    tool = FakeTypedTool()
    registry.register(tool)
    lc_tools = registry.get_langchain_tools(ToolFilter(categories=["test"]))
    lc_tool = lc_tools[0]
    result = await lc_tool.ainvoke({"ticker": "MSFT"})
    import json

    data = json.loads(result)
    assert data["ticker"] == "MSFT"


def test_build_schema_from_params_required_fields():
    """_build_schema_from_params creates correct required fields."""
    params = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "days": {"type": "integer", "description": "Look back days", "default": 7},
        },
        "required": ["query"],
    }
    schema = ToolRegistry._build_schema_from_params("test_tool", params)
    schema_json = schema.model_json_schema()
    assert "query" in schema_json["required"]
    assert schema_json["properties"]["query"]["type"] == "string"


def test_build_schema_from_params_optional_with_default():
    """_build_schema_from_params handles optional fields with defaults."""
    params = {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "Max results", "default": 20},
        },
    }
    schema = ToolRegistry._build_schema_from_params("screen_tool", params)
    instance = schema()
    assert instance.limit == 20


def test_build_schema_from_params_optional_without_default():
    """_build_schema_from_params makes fields without default nullable."""
    params = {
        "type": "object",
        "properties": {
            "sector": {"type": "string", "description": "Filter by sector"},
        },
    }
    schema = ToolRegistry._build_schema_from_params("filter_tool", params)
    instance = schema()
    assert instance.sector is None


def test_build_schema_from_params_generates_name():
    """_build_schema_from_params generates PascalCase model name."""
    params = {"type": "object", "properties": {}}
    schema = ToolRegistry._build_schema_from_params("get_geopolitical_events", params)
    assert schema.__name__ == "GetGeopoliticalEventsInput"


def test_get_langchain_tools_fallback_for_no_args_schema(registry):
    """get_langchain_tools() uses _build_schema_from_params for tools without args_schema."""
    tool = FakeTool("no_schema_tool", "test")
    tool.parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
        },
        "required": ["query"],
    }
    registry.register(tool)
    lc_tools = registry.get_langchain_tools(ToolFilter(categories=["test"]))
    assert len(lc_tools) == 1
    schema = lc_tools[0].args_schema.model_json_schema()
    assert "query" in schema["properties"]
    assert "kwargs" not in schema["properties"]


def test_all_internal_tools_have_args_schema():
    """All 7 internal tool classes define an explicit args_schema."""
    from backend.tools.analyze_stock import AnalyzeStockTool
    from backend.tools.compute_signals_tool import ComputeSignalsTool
    from backend.tools.geopolitical import GeopoliticalEventsTool
    from backend.tools.portfolio_exposure import PortfolioExposureTool
    from backend.tools.recommendations_tool import RecommendationsTool
    from backend.tools.screen_stocks import ScreenStocksTool
    from backend.tools.web_search import WebSearchTool

    tools = [
        AnalyzeStockTool,
        ComputeSignalsTool,
        GeopoliticalEventsTool,
        PortfolioExposureTool,
        RecommendationsTool,
        ScreenStocksTool,
        WebSearchTool,
    ]
    for tool_cls in tools:
        assert tool_cls.args_schema is not None, f"{tool_cls.__name__} missing args_schema"
        assert issubclass(tool_cls.args_schema, BaseModel), (
            f"{tool_cls.__name__}.args_schema is not a Pydantic BaseModel"
        )
