"use client";

import { useQuery } from "@tanstack/react-query";
import { get } from "@/lib/api";
import type { UserProfile } from "@/types/api";

export function useCurrentUser(enabled = true) {
  const query = useQuery({
    queryKey: ["current-user"],
    queryFn: () => get<UserProfile>("/auth/me"),
    staleTime: Infinity,
    enabled,
  });

  return {
    ...query,
    user: query.data ?? null,
    isAdmin: query.data?.role === "admin",
  };
}
