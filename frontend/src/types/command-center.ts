export interface DatabaseHealth {
  healthy: boolean;
  latency_ms: number;
  pool_active: number;
  pool_size: number;
  pool_overflow: number;
  migration_head: string | null;
}

export interface RedisHealth {
  healthy: boolean;
  latency_ms: number;
  memory_used_mb: number | null;
  memory_max_mb: number | null;
  total_keys: number | null;
}

export interface McpHealth {
  healthy: boolean;
  mode: string;
  tool_count: number;
  restarts: number;
  uptime_seconds: number | null;
}

export interface CeleryHealth {
  workers: number | null;
  queued: number | null;
  beat_active: boolean | null;
}

export interface LangfuseHealth {
  connected: boolean;
  traces_today: number;
  spans_today: number;
}

export interface SystemHealthZone {
  status: string;
  database: DatabaseHealth;
  redis: RedisHealth;
  mcp: McpHealth;
  celery: CeleryHealth;
  langfuse: LangfuseHealth;
}

export interface TopEndpoint {
  endpoint: string;
  count: number;
}

export interface ApiTrafficZone {
  window_seconds: number;
  sample_count: number;
  rps_avg: number;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
  latency_p99_ms: number | null;
  error_rate_pct: number | null;
  total_requests_today: number;
  total_errors_today: number;
  top_endpoints: TopEndpoint[];
}

export interface TierLatency {
  avg_ms?: number;
  p95_ms?: number;
}

export interface TierHealth {
  model: string;
  status: string;
  failures_5m: number;
  successes_5m: number;
  cascade_count: number;
  latency: TierLatency;
}

export interface TokenBudgetStatus {
  model: string;
  tpm_used_pct: number;
  rpm_used_pct: number;
}

export interface LlmOperationsZone {
  tiers: TierHealth[];
  cost_today_usd: number;
  cost_yesterday_usd: number;
  cost_week_usd: number;
  cascade_rate_pct: number;
  token_budgets: TokenBudgetStatus[];
}

export interface PipelineLastRun {
  started_at: string;
  status: string;
  total_duration_seconds: number | null;
  tickers_succeeded: number;
  tickers_failed: number;
  tickers_total: number;
  step_durations: Record<string, number> | null;
}

export interface PipelineWatermarkStatus {
  pipeline: string;
  last_date: string;
  status: string;
}

export interface PipelineZone {
  last_run: PipelineLastRun | null;
  watermarks: PipelineWatermarkStatus[];
  next_run_at: string | null;
}

export interface CommandCenterMeta {
  assembly_ms: number;
  degraded_zones: string[];
}

export interface CommandCenterResponse {
  timestamp: string;
  meta: CommandCenterMeta;
  system_health: SystemHealthZone | null;
  api_traffic: ApiTrafficZone | null;
  llm_operations: LlmOperationsZone | null;
  pipeline: PipelineZone | null;
}
