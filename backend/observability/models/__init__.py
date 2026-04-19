"""Observability models package — re-exports for convenient access.

Preserves legacy re-exports from backend.models.logs and adds the new
observability schema models. All models use ``__table_args__ = {"schema": "observability"}``
and must NOT be imported in ``backend/models/__init__.py`` — the observability
schema is created by Alembic DDL and does not participate in the main metadata registry.
"""

from backend.models.logs import LLMCallLog, ToolExecutionLog  # noqa: F401
from backend.observability.models.agent_intent_log import AgentIntentLog
from backend.observability.models.agent_reasoning_log import AgentReasoningLog
from backend.observability.models.api_error_log import ApiErrorLog
from backend.observability.models.auth_event_log import AuthEventLog
from backend.observability.models.beat_schedule_run import BeatScheduleRun
from backend.observability.models.cache_operation_log import CacheOperationLog
from backend.observability.models.celery_queue_depth import CeleryQueueDepth
from backend.observability.models.celery_worker_heartbeat import CeleryWorkerHeartbeat
from backend.observability.models.db_pool_event import DbPoolEvent as DbPoolEventModel
from backend.observability.models.deploy_events import DeployEvent
from backend.observability.models.email_send_log import EmailSendLog
from backend.observability.models.finding_log import FindingLog  # noqa: F401
from backend.observability.models.external_api_call import ExternalApiCallLog
from backend.observability.models.frontend_error_log import FrontendErrorLog
from backend.observability.models.oauth_event_log import OAuthEventLog
from backend.observability.models.provider_health_snapshot import ProviderHealthSnapshot
from backend.observability.models.rate_limiter_event import RateLimiterEvent
from backend.observability.models.request_log import RequestLog
from backend.observability.models.schema_migration_log import SchemaMigrationLog
from backend.observability.models.schema_versions import SchemaVersion
from backend.observability.models.slow_query_log import SlowQueryLog

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
    "SlowQueryLog",
    "DbPoolEventModel",
    "SchemaMigrationLog",
    "CacheOperationLog",
    "BeatScheduleRun",
    "CeleryQueueDepth",
    "CeleryWorkerHeartbeat",
    "AgentIntentLog",
    "AgentReasoningLog",
    "ProviderHealthSnapshot",
    "DeployEvent",
    "FrontendErrorLog",
    "FindingLog",
]
