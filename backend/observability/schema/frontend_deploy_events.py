"""Pydantic schemas for frontend error and deploy event observability.

FrontendErrorEvent extends ObsEventBase (SDK-routed via event_writer).
DeployEventData is standalone (written directly by the deploy endpoint, not via SDK).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.observability.schema.v1 import ObsEventBase


class FrontendErrorType(str, Enum):
    """Classification of frontend error origin."""

    UNHANDLED_REJECTION = "unhandled_rejection"
    REACT_ERROR_BOUNDARY = "react_error_boundary"
    QUERY_ERROR = "query_error"
    MUTATION_ERROR = "mutation_error"
    NETWORK_ERROR = "network_error"
    WINDOW_ERROR = "window_error"


class FrontendErrorEvent(ObsEventBase):
    """SDK event for a single frontend JavaScript error.

    Emitted by the beacon endpoint after receiving a batch of errors
    from the frontend observability-beacon library.

    Attributes:
        error_type: Classification of the error origin.
        error_message: Human-readable error message (truncated 1KB).
        error_stack: Stack trace (truncated 5KB).
        page_route: URL pathname where the error occurred.
        component_name: React component name from error boundary info.
        user_agent: Browser User-Agent string.
        url: Full URL or script filename.
        frontend_metadata: Additional context (JSONB).
    """

    error_type: FrontendErrorType
    error_message: str | None = Field(default=None, max_length=1024)
    error_stack: str | None = Field(default=None, max_length=5120)
    page_route: str | None = None
    component_name: str | None = None
    user_agent: str | None = None
    url: str | None = None
    frontend_metadata: dict | None = None


class DeployStatus(str, Enum):
    """Deploy outcome status."""

    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class DeployEventData(BaseModel):
    """Standalone Pydantic model for deploy events.

    Not an ObsEventBase subclass — deploy events are written directly
    by the deploy endpoint, not routed through the SDK.

    Attributes:
        git_sha: Git commit SHA of the deployed code.
        branch: Git branch that was deployed.
        pr_number: Pull request number, if applicable.
        author: GitHub actor who triggered the deploy.
        commit_message: Head commit message.
        migrations_applied: List of Alembic migration IDs applied.
        env: Target deployment environment.
        deploy_duration_seconds: Duration of the deploy in seconds.
        status: Deploy outcome.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    git_sha: str = Field(max_length=40)
    branch: str = Field(max_length=255)
    pr_number: int | None = None
    author: str = Field(max_length=255)
    commit_message: str | None = Field(default=None, max_length=1024)
    migrations_applied: list[str] | None = None
    env: Literal["dev", "staging", "prod"] = "staging"
    deploy_duration_seconds: float | None = None
    status: DeployStatus
    ts: datetime | None = None
