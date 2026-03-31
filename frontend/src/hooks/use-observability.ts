"use client";

import { useQuery } from "@tanstack/react-query";
import { get } from "@/lib/api";
import type {
  KPIResponse,
  QueryListResponse,
  QueryDetailResponse,
  GroupedResponse,
  AssessmentRunSummary,
  AssessmentHistoryResponse,
} from "@/types/api";

export const obsKeys = {
  kpis: ["observability", "kpis"] as const,
  queries: (params: Record<string, string | number | undefined>) =>
    ["observability", "queries", params] as const,
  queryDetail: (queryId: string) =>
    ["observability", "query-detail", queryId] as const,
  grouped: (params: Record<string, string | undefined>) =>
    ["observability", "grouped", params] as const,
  assessmentLatest: ["observability", "assessment", "latest"] as const,
  assessmentHistory: ["observability", "assessment", "history"] as const,
};

export function useObservabilityKPIs() {
  return useQuery({
    queryKey: obsKeys.kpis,
    queryFn: () => get<KPIResponse>("/observability/kpis"),
    staleTime: 60_000,
  });
}

interface QueryListParams {
  page?: number;
  size?: number;
  sort_by?: string;
  sort_order?: string;
  status?: string;
  cost_min?: number;
  cost_max?: number;
  date_from?: string;
  date_to?: string;
}

export function useObservabilityQueries(params: QueryListParams = {}) {
  const searchParams = new URLSearchParams();
  if (params.page != null) searchParams.set("page", String(params.page));
  if (params.size != null) searchParams.set("size", String(params.size));
  if (params.sort_by != null) searchParams.set("sort_by", params.sort_by);
  if (params.sort_order != null) searchParams.set("sort_order", params.sort_order);
  if (params.status != null) searchParams.set("status", params.status);
  if (params.cost_min != null)
    searchParams.set("cost_min", String(params.cost_min));
  if (params.cost_max != null)
    searchParams.set("cost_max", String(params.cost_max));
  if (params.date_from) searchParams.set("date_from", params.date_from);
  if (params.date_to) searchParams.set("date_to", params.date_to);
  const qs = searchParams.toString();
  const path = `/observability/queries${qs ? `?${qs}` : ""}`;

  return useQuery({
    queryKey: obsKeys.queries(
      params as Record<string, string | number | undefined>,
    ),
    queryFn: () => get<QueryListResponse>(path),
    staleTime: 60_000,
  });
}

export function useQueryDetail(queryId: string | null) {
  return useQuery({
    queryKey: obsKeys.queryDetail(queryId ?? ""),
    queryFn: () => get<QueryDetailResponse>(`/observability/queries/${queryId}`),
    staleTime: Infinity,
    enabled: !!queryId,
  });
}

interface GroupedParams {
  group_by: string;
  bucket?: string;
  date_from?: string;
  date_to?: string;
}

export function useObservabilityGrouped(params: GroupedParams) {
  const searchParams = new URLSearchParams();
  searchParams.set("group_by", params.group_by);
  if (params.bucket) searchParams.set("bucket", params.bucket);
  if (params.date_from) searchParams.set("date_from", params.date_from);
  if (params.date_to) searchParams.set("date_to", params.date_to);

  return useQuery({
    queryKey: obsKeys.grouped(params as unknown as Record<string, string | undefined>),
    queryFn: () =>
      get<GroupedResponse>(
        `/observability/queries/grouped?${searchParams.toString()}`,
      ),
    staleTime: 120_000,
  });
}

export function useAssessmentLatest() {
  return useQuery({
    queryKey: obsKeys.assessmentLatest,
    queryFn: () =>
      get<AssessmentRunSummary | null>("/observability/assessment/latest"),
    staleTime: 300_000,
  });
}

export function useAssessmentHistory(enabled = false) {
  return useQuery({
    queryKey: obsKeys.assessmentHistory,
    queryFn: () =>
      get<AssessmentHistoryResponse>("/observability/assessment/history"),
    staleTime: 300_000,
    enabled,
  });
}
