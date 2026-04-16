"""Observability models package — re-exports for convenient access.

Preserves legacy re-exports from backend.models.logs and adds
the new SchemaVersion model for event contract versioning.
"""

from backend.models.logs import LLMCallLog, ToolExecutionLog  # noqa: F401
from backend.observability.models.schema_versions import SchemaVersion

__all__ = ["LLMCallLog", "ToolExecutionLog", "SchemaVersion"]
