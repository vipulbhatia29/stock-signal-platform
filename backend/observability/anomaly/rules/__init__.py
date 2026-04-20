"""Anomaly rule registry."""

from backend.observability.anomaly.base import AnomalyRule
from backend.observability.anomaly.rules.db_pool_exhaustion import DbPoolExhaustionRule
from backend.observability.anomaly.rules.external_api_error_rate import ExternalApiErrorRateRule
from backend.observability.anomaly.rules.llm_cost_spike import LlmCostSpikeRule
from backend.observability.anomaly.rules.rate_limiter_fallback import RateLimiterFallbackRule
from backend.observability.anomaly.rules.slow_query_regression import SlowQueryRegressionRule
from backend.observability.anomaly.rules.watermark_staleness import WatermarkStalenessRule

ALL_RULES: list[AnomalyRule] = [
    ExternalApiErrorRateRule(),
    LlmCostSpikeRule(),
    SlowQueryRegressionRule(),
    DbPoolExhaustionRule(),
    RateLimiterFallbackRule(),
    WatermarkStalenessRule(),
]
