"""SQLAlchemy model for observability.deploy_events.

Records deployment events from CI/CD (GitHub Actions). Very low volume
(~1-5 per day) with 365d retention for long-term deploy correlation.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class DeployEvent(Base):
    """Row-per-deploy log for CI/CD deployment events.

    Attributes:
        id: Surrogate primary key (UUID, server-generated).
        ts: Wall-clock timestamp of the deploy event.
        git_sha: Git commit SHA of the deployed code.
        branch: Git branch that was deployed.
        pr_number: Pull request number, if applicable.
        author: GitHub actor who triggered the deploy.
        commit_message: Head commit message.
        migrations_applied: List of Alembic migration IDs applied (JSONB).
        env: Target deployment environment.
        deploy_duration_seconds: Duration of the deploy in seconds.
        status: Deploy outcome (success, failed, rolled_back).
    """

    __tablename__ = "deploy_events"
    __table_args__ = {"schema": "observability"}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    git_sha: Mapped[str] = mapped_column(Text, nullable=False)
    branch: Mapped[str] = mapped_column(Text, nullable=False)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    author: Mapped[str] = mapped_column(Text, nullable=False)
    commit_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    migrations_applied: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    env: Mapped[str] = mapped_column(Text, nullable=False)
    deploy_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
