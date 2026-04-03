"use client";

import { useQuery } from "@tanstack/react-query";
import { get } from "@/lib/api";

/** Fetch daily sentiment timeseries for a single ticker. */
export function useSentiment(ticker: string | null, days = 30) {
  return useQuery({
    queryKey: ["sentiment", ticker, days],
    queryFn: () =>
      get<{ ticker: string; data: unknown[] }>(
        `/sentiment/${ticker}?days=${days}`,
      ),
    enabled: !!ticker,
    staleTime: 30 * 60 * 1000, // 30 min — sentiment updates nightly
  });
}

/** Fetch bulk sentiment for all tracked tickers. */
export function useBulkSentiment(enabled = true) {
  return useQuery({
    queryKey: ["sentiment", "bulk"],
    queryFn: () => get<unknown[]>("/sentiment/bulk"),
    staleTime: 30 * 60 * 1000,
    enabled,
  });
}

/** Fetch macro-level sentiment timeseries. */
export function useMacroSentiment(days = 30) {
  return useQuery({
    queryKey: ["sentiment", "macro", days],
    queryFn: () =>
      get<{ ticker: string; data: unknown[] }>(
        `/sentiment/macro?days=${days}`,
      ),
    staleTime: 30 * 60 * 1000,
  });
}
