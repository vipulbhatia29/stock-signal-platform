"""Anomaly rule registry."""

from backend.observability.anomaly.base import AnomalyRule
from backend.observability.anomaly.rules.agent_decline_rate import AgentDeclineRateRule
from backend.observability.anomaly.rules.beat_schedule_drift import BeatScheduleDriftRule
from backend.observability.anomaly.rules.db_pool_exhaustion import DbPoolExhaustionRule
from backend.observability.anomaly.rules.dq_critical_findings import DqCriticalFindingsRule
from backend.observability.anomaly.rules.external_api_error_rate import ExternalApiErrorRateRule
from backend.observability.anomaly.rules.frontend_error_burst import FrontendErrorBurstRule
from backend.observability.anomaly.rules.http_5xx_elevated import Http5xxElevatedRule
from backend.observability.anomaly.rules.llm_cost_spike import LlmCostSpikeRule
from backend.observability.anomaly.rules.rate_limiter_fallback import RateLimiterFallbackRule
from backend.observability.anomaly.rules.slow_query_regression import SlowQueryRegressionRule
from backend.observability.anomaly.rules.watermark_staleness import WatermarkStalenessRule
from backend.observability.anomaly.rules.worker_heartbeat_missing import WorkerHeartbeatMissingRule

ALL_RULES: list[AnomalyRule] = [
    ExternalApiErrorRateRule(),
    LlmCostSpikeRule(),
    SlowQueryRegressionRule(),
    DbPoolExhaustionRule(),
    RateLimiterFallbackRule(),
    WatermarkStalenessRule(),
    WorkerHeartbeatMissingRule(),
    BeatScheduleDriftRule(),
    Http5xxElevatedRule(),
    FrontendErrorBurstRule(),
    DqCriticalFindingsRule(),
    AgentDeclineRateRule(),
]
