"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { get, patch } from "@/lib/api";
import type {
  AdminKpisEnvelope,
  AdminErrorsEnvelope,
  AdminFindingsEnvelope,
  Finding,
  AdminExternalsEnvelope,
  AdminCostsEnvelope,
  PipelineDiagnosticEnvelope,
  DqFindingsEnvelope,
} from "@/types/admin-observability";

export const adminObsKeys = {
  kpis: (windowMin: number) => ["admin-obs", "kpis", windowMin] as const,
  errors: (params: Record<string, string | number | undefined>) =>
    ["admin-obs", "errors", params] as const,
  findings: (params: Record<string, string | number | undefined>) =>
    ["admin-obs", "findings", params] as const,
  trace: (traceId: string) => ["admin-obs", "trace", traceId] as const,
  externals: (provider: string, windowMin: number) =>
    ["admin-obs", "externals", provider, windowMin] as const,
  costs: (params: Record<string, string | number | undefined>) =>
    ["admin-obs", "costs", params] as const,
  pipelines: (name: string, recentN: number) =>
    ["admin-obs", "pipelines", name, recentN] as const,
  dq: (params: Record<string, string | number | undefined>) =>
    ["admin-obs", "dq", params] as const,
};

export function useAdminKpis(windowMin = 60) {
  return useQuery<AdminKpisEnvelope>({
    queryKey: adminObsKeys.kpis(windowMin),
    queryFn: () =>
      get<AdminKpisEnvelope>(
        `/observability/admin/kpis?window_min=${windowMin}`
      ),
    refetchInterval: 15_000,
    refetchOnWindowFocus: true,
    staleTime: 0,
  });
}

export interface AdminErrorsParams {
  subsystem?: string;
  severity?: string;
  user_id?: string;
  ticker?: string;
  since?: string;
  limit?: number;
}

export function useAdminErrors(params: AdminErrorsParams = {}) {
  const {
    subsystem, severity, user_id, ticker,
    since = "1h", limit = 50,
  } = params;

  const qs = new URLSearchParams();
  if (subsystem) qs.set("subsystem", subsystem);
  if (severity) qs.set("severity", severity);
  if (user_id) qs.set("user_id", user_id);
  if (ticker) qs.set("ticker", ticker);
  qs.set("since", since);
  qs.set("limit", String(limit));

  const queryParams: Record<string, string | number | undefined> = {
    subsystem, severity, user_id, ticker, since, limit,
  };

  return useQuery<AdminErrorsEnvelope>({
    queryKey: adminObsKeys.errors(queryParams),
    queryFn: () =>
      get<AdminErrorsEnvelope>(`/observability/admin/errors?${qs.toString()}`),
    refetchInterval: 15_000,
    refetchOnWindowFocus: true,
    staleTime: 0,
  });
}

export function useAdminFindings(params: {
  status?: string;
  severity?: string;
  attribution_layer?: string;
  since?: string;
  limit?: number;
}) {
  const searchParams = new URLSearchParams();
  if (params.status) searchParams.set("status", params.status);
  if (params.severity) searchParams.set("severity", params.severity);
  if (params.attribution_layer) searchParams.set("attribution_layer", params.attribution_layer);
  if (params.since) searchParams.set("since", params.since);
  if (params.limit) searchParams.set("limit", String(params.limit));
  const qs = searchParams.toString();
  const path = `/observability/admin/findings${qs ? `?${qs}` : ""}`;
  const key = adminObsKeys.findings(params as Record<string, string | number | undefined>);

  return useQuery<AdminFindingsEnvelope>({
    queryKey: key,
    queryFn: () => get<AdminFindingsEnvelope>(path),
    refetchInterval: 15_000,
    refetchOnWindowFocus: true,
    staleTime: 0,
  });
}

export function useAcknowledgeFinding() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (findingId: string) =>
      patch<Finding>(`/observability/admin/findings/${findingId}/acknowledge`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-obs", "findings"] });
    },
  });
}

export function useSuppressFinding() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (findingId: string) =>
      patch<Finding>(
        `/observability/admin/findings/${findingId}/suppress?duration=1h`
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-obs", "findings"] });
    },
  });
}

export function useAdminExternals(provider: string, windowMin = 60) {
  return useQuery<AdminExternalsEnvelope>({
    queryKey: adminObsKeys.externals(provider, windowMin),
    queryFn: () =>
      get<AdminExternalsEnvelope>(
        `/observability/admin/externals?provider=${encodeURIComponent(provider)}&window_min=${windowMin}&compare_to=prior_window`
      ),
    enabled: provider.length > 0,
    refetchInterval: 15_000,
    refetchOnWindowFocus: true,
    staleTime: 0,
  });
}

export function useAdminCosts(
  window = "7d",
  by: "provider" | "model" | "tier" | "user" = "provider",
  limit = 50
) {
  return useQuery<AdminCostsEnvelope>({
    queryKey: adminObsKeys.costs({ window, by, limit }),
    queryFn: () =>
      get<AdminCostsEnvelope>(
        `/observability/admin/costs?window=${encodeURIComponent(window)}&by=${by}&limit=${limit}&compare_to=prior_window`
      ),
    refetchInterval: 15_000,
    refetchOnWindowFocus: true,
    staleTime: 0,
  });
}

export function useAdminPipelines(pipelineName: string, recentN = 5) {
  return useQuery<PipelineDiagnosticEnvelope>({
    queryKey: adminObsKeys.pipelines(pipelineName, recentN),
    queryFn: () =>
      get<PipelineDiagnosticEnvelope>(
        `/observability/admin/pipelines?pipeline_name=${encodeURIComponent(pipelineName)}&recent_n=${recentN}`
      ),
    enabled: pipelineName.length > 0,
    refetchInterval: 15_000,
    refetchOnWindowFocus: true,
    staleTime: 0,
  });
}

export function useAdminDq(params: {
  severity?: string;
  check?: string;
  ticker?: string;
  since?: string;
  limit?: number;
} = {}) {
  const { severity, check, ticker, since = "24h", limit = 50 } = params;
  const qp = new URLSearchParams({ since, limit: String(limit) });
  if (severity) qp.set("severity", severity);
  if (check) qp.set("check", check);
  if (ticker) qp.set("ticker", ticker);

  return useQuery<DqFindingsEnvelope>({
    queryKey: adminObsKeys.dq({ severity, check, ticker, since, limit }),
    queryFn: () =>
      get<DqFindingsEnvelope>(`/observability/admin/dq?${qp.toString()}`),
    refetchInterval: 15_000,
    refetchOnWindowFocus: true,
    staleTime: 0,
  });
}
