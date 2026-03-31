/* ----- API Traffic Drill-Down ----- */

export interface ApiTrafficDrillDown {
  window_seconds: number;
  endpoints: { endpoint: string; count: number }[];
  total_requests_today: number;
  total_errors_today: number;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
  latency_p99_ms: number | null;
  error_rate_pct: number | null;
  sample_count: number;
}

/* ----- LLM Drill-Down ----- */

export interface LlmModelBreakdown {
  model: string;
  provider: string;
  call_count: number;
  total_cost_usd: number;
  avg_latency_ms: number;
  error_count: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
}

export interface CascadeEntry {
  model: string;
  error: string;
  timestamp: string;
}

export interface LlmDrillDown {
  hours: number;
  models: LlmModelBreakdown[];
  cascades: CascadeEntry[];
  total_models: number;
}

/* ----- Pipeline Drill-Down ----- */

export interface PipelineRunEntry {
  id: string;
  pipeline_name: string;
  started_at: string;
  completed_at: string | null;
  status: string;
  total_duration_seconds: number | null;
  tickers_succeeded: number;
  tickers_failed: number;
  tickers_total: number;
  error_summary: Record<string, string> | null;
  step_durations: Record<string, number> | null;
}

export interface PipelineDrillDown {
  runs: PipelineRunEntry[];
  total: number;
  days: number;
}
