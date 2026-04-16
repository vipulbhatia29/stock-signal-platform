"""Skeleton for 1c's MCP tool — returns active schema version + event type list.

1c adds: table list with row counts + retention, enum registry, tool manifest.
Keeping the skeleton here so agents calling it at session start don't break mid-1a.
"""
from __future__ import annotations
from sqlalchemy import text
from backend.database import async_session_factory
from backend.observability.schema.v1 import EventType


async def describe_observability_schema() -> dict:
    async with async_session_factory() as db:
        row = (await db.execute(text(
            "SELECT version FROM observability.schema_versions ORDER BY applied_at DESC LIMIT 1"
        ))).scalar()
    return {
        "schema_version": row or "unknown",
        "event_types": [e.value for e in EventType],
    }
