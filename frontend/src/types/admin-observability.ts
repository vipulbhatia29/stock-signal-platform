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
