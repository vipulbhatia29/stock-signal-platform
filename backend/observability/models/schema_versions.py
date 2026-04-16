"""SchemaVersion model — pointer to the active Pydantic event contract version.

describe_observability_schema() MCP tool reads the most recent row to report
which Pydantic schema version (v1, v2, ...) agents should expect.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class SchemaVersion(Base):
    __tablename__ = "schema_versions"
    __table_args__ = {"schema": "observability"}

    version: Mapped[str] = mapped_column(Text, primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
