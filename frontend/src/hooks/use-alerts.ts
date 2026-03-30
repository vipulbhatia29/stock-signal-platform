"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { get, patch } from "@/lib/api";
import type { AlertListResponse } from "@/types/api";

/** Fetch all alerts for the current user. */
export function useAlerts() {
  return useQuery({
    queryKey: ["alerts"],
    queryFn: () => get<AlertListResponse>("/alerts"),
    staleTime: 60 * 1000,
    select: (data) => ({
      alerts: data.alerts,
      total: data.total,
      unreadCount: data.unread_count,
    }),
  });
}

/** Mark alerts as read. */
export function useMarkAlertsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (alertIds: string[]) =>
      patch<void>("/alerts/read", { alert_ids: alertIds }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
  });
}
