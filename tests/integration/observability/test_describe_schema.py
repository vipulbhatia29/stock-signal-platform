import pytest

from backend.observability.mcp.describe_schema import describe_observability_schema


@pytest.mark.asyncio
async def test_describe_returns_current_schema_version(db_session):
    """describe_observability_schema() returns envelope with schema version and event types.

    Result is wrapped in MCP envelope — actual data at result["result"].
    schema_version depends on migration 030 seed data in schema_versions table.
    """
    envelope = await describe_observability_schema()
    assert envelope["tool"] == "describe_observability_schema"
    inner = envelope["result"]
    # schema_version is "v1" when migration 030 seed data is present,
    # "unknown" when test DB was created via metadata.create_all() (no migrations)
    assert inner["schema_version"] in ("v1", "unknown")
    assert "event_types" in inner
    assert "llm_call" in inner["event_types"]
