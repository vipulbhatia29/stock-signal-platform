"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { get, patch } from "@/lib/api";
import type { AlertResponse, UnreadAlertCount } from "@/types/api";

/** Fetch all alerts for the current user. */
export function useAlerts() {
  return useQuery({
    queryKey: ["alerts"],
    queryFn: () => get<AlertResponse[]>("/alerts"),
    staleTime: 60 * 1000, // 1 min
  });
}

/** Fetch unread alert count. */
export function useUnreadAlertCount() {
  return useQuery({
    queryKey: ["alerts", "unread-count"],
    queryFn: () => get<UnreadAlertCount>("/alerts/unread-count"),
    staleTime: 30 * 1000, // 30 sec — for badge updates
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
