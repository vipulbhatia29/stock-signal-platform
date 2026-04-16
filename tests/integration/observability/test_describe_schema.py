import pytest

from backend.observability.mcp.describe_schema import describe_observability_schema


@pytest.mark.asyncio
async def test_describe_returns_current_schema_version(db_session):
    result = await describe_observability_schema()
    assert result["schema_version"] == "v1"
    assert "event_types" in result
    assert "llm_call" in result["event_types"]
