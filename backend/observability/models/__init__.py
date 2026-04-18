"""Observability models package — re-exports for convenient access.

Preserves legacy re-exports from backend.models.logs and adds the new
observability schema models: SchemaVersion, ExternalApiCallLog, RateLimiterEvent,
RequestLog, ApiErrorLog, AuthEventLog, OAuthEventLog, EmailSendLog.

Note: These models use ``__table_args__ = {"schema": "observability"}`` and must
NOT be imported in ``backend/models/__init__.py`` — the observability schema is
created by Alembic DDL and does not participate in the main metadata registry.
"""

from backend.models.logs import LLMCallLog, ToolExecutionLog  # noqa: F401
from backend.observability.models.api_error_log import ApiErrorLog
from backend.observability.models.auth_event_log import AuthEventLog
from backend.observability.models.email_send_log import EmailSendLog
from backend.observability.models.external_api_call import ExternalApiCallLog
from backend.observability.models.oauth_event_log import OAuthEventLog
from backend.observability.models.rate_limiter_event import RateLimiterEvent
from backend.observability.models.request_log import RequestLog
from backend.observability.models.schema_versions import SchemaVersion

__all__ = [
    "LLMCallLog",
    "ToolExecutionLog",
    "SchemaVersion",
    "ExternalApiCallLog",
    "RateLimiterEvent",
    "RequestLog",
    "ApiErrorLog",
    "AuthEventLog",
    "OAuthEventLog",
    "EmailSendLog",
]
