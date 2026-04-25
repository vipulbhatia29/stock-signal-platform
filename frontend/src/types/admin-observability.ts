/** Type definitions for the admin observability dashboard endpoints. */

/** Standard MCP envelope returned by all admin observability endpoints. */
export interface AdminObsEnvelope<T> {
  tool: string;
  window: { from: string; to: string };
  result: T;
  meta: { total_count: number; truncated: boolean; schema_version: string };
}

/** Per-subsystem health status. */
export interface SubsystemHealth {
  status: "healthy" | "degraded" | "failing";
  [key: string]: unknown;
}

/** Result shape for GET /observability/admin/kpis. */
export interface AdminKpisResult {
  overall_status: "healthy" | "degraded" | "failing";
  subsystems: Record<string, SubsystemHealth>;
  open_anomalies?: { total: number; by_severity: Record<string, number> };
}

export type AdminKpisEnvelope = AdminObsEnvelope<AdminKpisResult>;

// ---------------------------------------------------------------------------
// Zone 2: Error Stream
// ---------------------------------------------------------------------------

export interface ErrorEntry {
  source: "http" | "external_api" | "tool" | "celery" | "frontend";
  ts: string;
  message: string | null;
  severity: "error" | "warning";
  trace_id: string | null;
  stack_signature: string | null;
  details: Record<string, unknown>;
}

export interface AdminErrorsResult {
  errors: ErrorEntry[];
}

export type AdminErrorsEnvelope = AdminObsEnvelope<AdminErrorsResult>;

// ---------------------------------------------------------------------------
// Zone 3: Anomaly Findings
// ---------------------------------------------------------------------------

export type FindingSeverity = "critical" | "error" | "warning" | "info";
export type FindingStatus = "open" | "acknowledged" | "resolved" | "suppressed";

export interface Finding {
  id: string;
  kind: string;
  attribution_layer: string;
  severity: FindingSeverity;
  status: FindingStatus;
  title: string;
  evidence: Record<string, unknown>;
  remediation_hint: string | null;
  related_traces: string[] | null;
  opened_at: string | null;
  closed_at: string | null;
  dedup_key: string;
  jira_ticket_key: string | null;
  negative_check_count: number;
  acknowledged_by?: string | null;
  acknowledged_at?: string | null;
  suppressed_until?: string | null;
  suppression_reason?: string | null;
}

export interface AdminFindingsResult {
  findings: Finding[];
}

export type AdminFindingsEnvelope = AdminObsEnvelope<AdminFindingsResult>;

// ---------------------------------------------------------------------------
// Zone 5: External API
// ---------------------------------------------------------------------------

export interface ExternalApiStats {
  call_count: number;
  success_count: number;
  error_count: number;
  success_rate: number | null;
  p50_latency_ms: number | null;
  p95_latency_ms: number | null;
  total_cost_usd: number | null;
}

export interface ExternalApiErrorEntry {
  error_reason: string;
  count: number;
}

export interface ExternalApiDeltas {
  call_count: number | null;
  success_count: number | null;
  error_count: number | null;
  success_rate: number | null;
  p50_latency_ms: number | null;
  p95_latency_ms: number | null;
  total_cost_usd: number | null;
}

export interface AdminExternalsResult {
  provider: string;
  window_min: number;
  stats: ExternalApiStats;
  error_breakdown: ExternalApiErrorEntry[];
  rate_limit_events: number;
  prior_window?: ExternalApiStats;
  deltas?: ExternalApiDeltas;
}

export type AdminExternalsEnvelope = AdminObsEnvelope<AdminExternalsResult>;

// ---------------------------------------------------------------------------
// Zone 6: Cost Breakdown
// ---------------------------------------------------------------------------

export interface CostGroup {
  [dimension: string]: string | number | null | undefined;
  total_cost_usd: number | null;
  call_count: number;
  avg_cost_per_call: number | null;
  p95_latency_ms: number | null;
  prior_total_cost_usd?: number | null;
  prior_call_count?: number | null;
  delta_cost_usd?: number | null;
  delta_call_count?: number | null;
}

export interface AdminCostsResult {
  by: string;
  groups: CostGroup[];
}

export type AdminCostsEnvelope = AdminObsEnvelope<AdminCostsResult>;

// ---------------------------------------------------------------------------
// Zone 7: Pipeline Health
// ---------------------------------------------------------------------------

export interface PipelineRun {
  id: string;
  pipeline_name: string;
  started_at: string | null;
  completed_at: string | null;
  status: "success" | "failed" | "running" | string;
  tickers_total: number;
  tickers_succeeded: number;
  tickers_failed: number;
  error_summary: string | null;
  step_durations: Record<string, number> | null;
  total_duration_seconds: number | null;
  retry_count: number;
}

export interface PipelineWatermark {
  pipeline_name: string;
  last_completed_date: string | null;
  last_completed_at: string | null;
  status: string;
}

export interface PipelineFailurePattern {
  consecutive_failures: number;
  is_currently_failing: boolean;
}

export interface PipelineDiagnosticResult {
  pipeline_name: string;
  runs: PipelineRun[];
  watermark: PipelineWatermark | null;
  failure_pattern: PipelineFailurePattern;
  ticker_success_rate: number | null;
}

export type PipelineDiagnosticEnvelope = AdminObsEnvelope<PipelineDiagnosticResult>;

// ---------------------------------------------------------------------------
// Zone 8: DQ Scanner
// ---------------------------------------------------------------------------

export interface DqFinding {
  check_name: string;
  severity: "critical" | "warning" | "info" | string;
  ticker: string | null;
  message: string;
  metadata: Record<string, unknown> | null;
  detected_at: string | null;
}

export interface DqFindingsResult {
  findings: DqFinding[];
}

export type DqFindingsEnvelope = AdminObsEnvelope<DqFindingsResult>;
