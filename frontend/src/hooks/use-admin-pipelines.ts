"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { get, post } from "@/lib/api";

// Types
export interface TaskDefinition {
  name: string;
  display_name: string;
  group: string;
  order: number;
  is_seed: boolean;
  schedule: string;
  estimated_duration: string;
  idempotent: boolean;
  incremental: boolean;
  rationale: string;
  depends_on: string[];
}

export interface PipelineGroup {
  name: string;
  tasks: TaskDefinition[];
  execution_plan: string[][];
}

export interface PipelineGroupList {
  groups: PipelineGroup[];
}

export interface PipelineRun {
  run_id: string;
  group: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  task_names: string[];
  completed: number;
  failed: number;
  total: number;
  task_statuses: Record<string, string>;
  errors: Record<string, string>;
}

export interface RunHistory {
  group: string;
  runs: PipelineRun[];
}

export interface TriggerResponse {
  group: string;
  status: string;
  message: string;
}

export interface CacheClearResponse {
  pattern: string;
  keys_deleted: number;
  message: string;
}

// Query keys
export const pipelineKeys = {
  groups: ["admin-pipelines", "groups"] as const,
  group: (name: string) => ["admin-pipelines", "groups", name] as const,
  activeRun: (group: string) => ["admin-pipelines", "active-run", group] as const,
  run: (runId: string) => ["admin-pipelines", "run", runId] as const,
  history: (group: string) => ["admin-pipelines", "history", group] as const,
};

// Hooks
export function usePipelineGroups() {
  return useQuery<PipelineGroupList>({
    queryKey: pipelineKeys.groups,
    queryFn: () => get<PipelineGroupList>("/admin/pipelines/groups"),
    staleTime: 60_000, // Groups don't change often
  });
}

export function useActiveRun(group: string) {
  return useQuery<PipelineRun | null>({
    queryKey: pipelineKeys.activeRun(group),
    queryFn: () => get<PipelineRun | null>(`/admin/pipelines/groups/${group}/runs`),
    refetchInterval: (query) =>
      query.state.data ? 3_000 : 30_000, // Fast poll when active, slow when idle
    enabled: !!group,
  });
}

export function useRunHistory(group: string, limit = 10) {
  return useQuery<RunHistory>({
    queryKey: pipelineKeys.history(group),
    queryFn: () => get<RunHistory>(`/admin/pipelines/groups/${group}/history?limit=${limit}`),
    staleTime: 10_000,
    enabled: !!group,
  });
}

export function useTriggerGroup() {
  const queryClient = useQueryClient();
  return useMutation<TriggerResponse, Error, { group: string; failureMode?: string }>({
    mutationFn: ({ group, failureMode = "continue" }) =>
      post<TriggerResponse>(`/admin/pipelines/groups/${group}/run`, {
        failure_mode: failureMode,
      }),
    onSuccess: (_, { group }) => {
      queryClient.invalidateQueries({ queryKey: pipelineKeys.activeRun(group) });
      queryClient.invalidateQueries({ queryKey: pipelineKeys.history(group) });
    },
  });
}

export function useClearCache() {
  return useMutation<CacheClearResponse, Error, { pattern: string }>({
    mutationFn: ({ pattern }) =>
      post<CacheClearResponse>("/admin/pipelines/cache/clear", { pattern }),
  });
}

export function useClearAllCaches() {
  return useMutation<CacheClearResponse, Error, void>({
    mutationFn: () => post<CacheClearResponse>("/admin/pipelines/cache/clear-all", {}),
  });
}
