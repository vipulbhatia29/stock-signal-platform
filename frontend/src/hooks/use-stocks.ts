"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { get, post, del } from "@/lib/api";
import { toast } from "sonner";
import type {
  IndexResponse,
  WatchlistItem,
  StockSearchResponse,
  IngestResponse,
  BulkSignalsResponse,
  PricePoint,
  SignalResponse,
  SignalHistoryItem,
  PricePeriod,
} from "@/types/api";

// ── Indexes ───────────────────────────────────────────────────────────────────

export function useIndexes() {
  return useQuery({
    queryKey: ["indexes"],
    queryFn: () => get<IndexResponse[]>("/indexes"),
    staleTime: 5 * 60 * 1000,
  });
}

// ── Watchlist ─────────────────────────────────────────────────────────────────

export function useWatchlist() {
  return useQuery({
    queryKey: ["watchlist"],
    queryFn: () => get<WatchlistItem[]>("/stocks/watchlist"),
    staleTime: 30 * 1000,
  });
}

export function useAddToWatchlist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ticker: string) =>
      post<WatchlistItem>("/stocks/watchlist", { ticker }),
    onSuccess: (_data, ticker) => {
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
      toast.success(`${ticker.toUpperCase()} added to watchlist`);
    },
    onError: (err) => {
      toast.error(err instanceof Error ? err.message : "Failed to add");
    },
  });
}

export function useRemoveFromWatchlist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ticker: string) => del<void>(`/stocks/watchlist/${ticker}`),
    onMutate: async (ticker) => {
      await queryClient.cancelQueries({ queryKey: ["watchlist"] });
      const previous = queryClient.getQueryData<WatchlistItem[]>(["watchlist"]);
      queryClient.setQueryData<WatchlistItem[]>(["watchlist"], (old) =>
        old?.filter((item) => item.ticker !== ticker)
      );
      return { previous };
    },
    onError: (_err, _ticker, context) => {
      queryClient.setQueryData(["watchlist"], context?.previous);
      toast.error("Failed to remove from watchlist");
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });
}

// ── Stock Search ──────────────────────────────────────────────────────────────

export function useStockSearch(query: string) {
  return useQuery({
    queryKey: ["stock-search", query],
    queryFn: () =>
      get<StockSearchResponse[]>(
        `/stocks/search?q=${encodeURIComponent(query)}`
      ),
    enabled: query.length >= 1,
    staleTime: 30 * 1000,
  });
}

// ── Ingestion ─────────────────────────────────────────────────────────────────

export function useIngestTicker() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ticker: string) =>
      post<IngestResponse>(`/stocks/${ticker}/ingest`),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["signals", data.ticker] });
      queryClient.invalidateQueries({ queryKey: ["prices", data.ticker] });
    },
  });
}

// ── Bulk Signals (Screener) ───────────────────────────────────────────────────

export interface ScreenerFilters {
  index?: string;
  rsi_state?: string;
  macd_state?: string;
  sector?: string;
  score_min?: number;
  score_max?: number;
  sort_by?: string;
  sort_order?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

function buildScreenerQuery(filters: ScreenerFilters): string {
  const params = new URLSearchParams();
  if (filters.index) params.set("index", filters.index);
  if (filters.rsi_state) params.set("rsi_state", filters.rsi_state);
  if (filters.macd_state) params.set("macd_state", filters.macd_state);
  if (filters.sector) params.set("sector", filters.sector);
  if (filters.score_min !== undefined)
    params.set("score_min", String(filters.score_min));
  if (filters.score_max !== undefined)
    params.set("score_max", String(filters.score_max));
  if (filters.sort_by) params.set("sort_by", filters.sort_by);
  if (filters.sort_order) params.set("sort_order", filters.sort_order);
  params.set("limit", String(filters.limit ?? 50));
  params.set("offset", String(filters.offset ?? 0));
  return params.toString();
}

export function useBulkSignals(filters: ScreenerFilters) {
  return useQuery({
    queryKey: ["bulk-signals", filters],
    queryFn: () =>
      get<BulkSignalsResponse>(
        `/stocks/signals/bulk?${buildScreenerQuery(filters)}`
      ),
    placeholderData: (prev) => prev,
    staleTime: 60 * 1000,
  });
}

// ── Prices ────────────────────────────────────────────────────────────────────

export function usePrices(ticker: string, period: PricePeriod) {
  return useQuery({
    queryKey: ["prices", ticker, period],
    queryFn: () =>
      get<PricePoint[]>(`/stocks/${ticker}/prices?period=${period}`),
    staleTime: 5 * 60 * 1000,
  });
}

// ── Signals ───────────────────────────────────────────────────────────────────

export function useSignals(ticker: string) {
  return useQuery({
    queryKey: ["signals", ticker],
    queryFn: () => get<SignalResponse>(`/stocks/${ticker}/signals`),
    staleTime: 5 * 60 * 1000,
  });
}

// ── Signal History ────────────────────────────────────────────────────────────

export function useSignalHistory(ticker: string, days = 90) {
  return useQuery({
    queryKey: ["signal-history", ticker, days],
    queryFn: () =>
      get<SignalHistoryItem[]>(
        `/stocks/${ticker}/signals/history?days=${days}`
      ),
    staleTime: 10 * 60 * 1000,
  });
}

// ── Watchlist membership check (derived) ──────────────────────────────────────

export function useIsInWatchlist(ticker: string): boolean {
  const { data } = useWatchlist();
  return data?.some((item) => item.ticker === ticker) ?? false;
}

// ── Stock meta (name/sector) derived from watchlist cache ─────────────────────

export function useStockMeta(ticker: string): {
  name: string | null;
  sector: string | null;
} {
  const { data: watchlist } = useWatchlist();
  const item = watchlist?.find((w) => w.ticker === ticker);
  return { name: item?.name ?? null, sector: item?.sector ?? null };
}
