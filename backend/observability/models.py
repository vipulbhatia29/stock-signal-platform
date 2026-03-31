"""Observability log models — canonical imports from backend.models.logs.

Alembic model discovery requires these models to be importable via
backend/models/__init__.py, so the original file remains authoritative.
This module provides a convenient import path within the observability package.
"""

from backend.models.logs import LLMCallLog, ToolExecutionLog  # noqa: F401
