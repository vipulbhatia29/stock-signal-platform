"use client";

import { useQuery } from "@tanstack/react-query";
import { get } from "@/lib/api";
import type { CommandCenterResponse } from "@/types/command-center";

export const commandCenterKeys = {
  aggregate: ["command-center"] as const,
  drillDown: (zone: string) => ["command-center", zone] as const,
};

export function useCommandCenter() {
  return useQuery<CommandCenterResponse>({
    queryKey: commandCenterKeys.aggregate,
    queryFn: () => get<CommandCenterResponse>("/admin/command-center"),
    refetchInterval: 15_000,
    refetchOnWindowFocus: true,
    staleTime: 10_000,
  });
}

export function useCommandCenterDrillDown<T>(zone: string, enabled = false) {
  return useQuery<T>({
    queryKey: commandCenterKeys.drillDown(zone),
    queryFn: () => get<T>(`/admin/command-center/${zone}`),
    enabled,
    staleTime: 30_000,
  });
}
