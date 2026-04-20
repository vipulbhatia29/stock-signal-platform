"use client";

import { useQuery } from "@tanstack/react-query";
import { get } from "@/lib/api";
import type { AdminKpisEnvelope } from "@/types/admin-observability";

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
