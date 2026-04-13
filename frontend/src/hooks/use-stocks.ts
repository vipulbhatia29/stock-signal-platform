"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { get, post, patch, del } from "@/lib/api";
import { toast } from "sonner";
import type {
  DividendSummary,
  IndexResponse,
  WatchlistItem,
  StockSearchResponse,
  IngestResponse,
  BulkSignalsResponse,
  FundamentalsResponse,
  PricePoint,
  SignalResponse,
  SignalHistoryItem,
  PricePeriod,
  UserPreferences,
  UserPreferencesUpdate,
  RebalancingResponse,
  Position,
  PortfolioSummary,
  PortfolioSnapshot,
  Recommendation,
  PaginatedRecommendations,
  StockNewsResponse,
  StockIntelligenceResponse,
  BenchmarkComparisonResponse,
  OHLCResponse,
  MarketBriefingResult,
  PortfolioHealthResult,
  DashboardNewsResponse,
  PortfolioAnalyticsResponse,
  StockAnalyticsResponse,
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
      // Invalidate watchlist + downstream caches populated by auto-ingest
      // Toasts are handled by the caller (layout.tsx handleAddTicker)
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
      queryClient.invalidateQueries({ queryKey: ["stocks"] });
      queryClient.invalidateQueries({ queryKey: ["signals", ticker.toUpperCase()] });
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
      const tickerKeys = [
        ["signals", data.ticker],
        ["prices", data.ticker],
        ["fundamentals", data.ticker],
        ["stock-news", data.ticker],
        ["stock-intelligence", data.ticker],
        ["forecast", data.ticker],
        ["benchmark", data.ticker],
        ["stock-analytics", data.ticker],
        ["ingest-state", data.ticker],
      ];
      for (const key of tickerKeys) {
        queryClient.invalidateQueries({ queryKey: key });
      }
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
      queryClient.invalidateQueries({ queryKey: ["bulk-signals"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio", "positions"] });
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : String(error);
      if (message.includes("429") || message.includes("rate limit")) {
        toast.error("Hourly ingest limit reached. Try again later.");
      }
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

export function useTrendingStocks(limit = 5) {
  return useQuery({
    queryKey: ["trending-stocks", limit],
    queryFn: () =>
      get<BulkSignalsResponse>(
        `/stocks/signals/bulk?sort_by=composite_score&sort_order=desc&limit=${limit}`
      ),
    staleTime: 5 * 60 * 1000,
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
    refetchInterval: (query) => {
      // Poll every 5s while signals are refreshing, stop when fresh
      const data = query.state.data;
      return data?.is_refreshing ? 5000 : false;
    },
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

// ── Fundamentals ──────────────────────────────────────────────────────────────

export function useFundamentals(ticker: string) {
  return useQuery({
    queryKey: ["fundamentals", ticker],
    queryFn: () => get<FundamentalsResponse>(`/stocks/${ticker}/fundamentals`),
    staleTime: 15 * 60 * 1000, // Fundamentals change slowly — cache 15 min
    retry: 1,
  });
}

// ── Dividends ────────────────────────────────────────────────────────────────

export function useDividends(ticker: string) {
  return useQuery({
    queryKey: ["dividends", ticker],
    queryFn: () => get<DividendSummary>(`/portfolio/dividends/${ticker}`),
    staleTime: 30 * 60 * 1000, // Dividends change infrequently — cache 30 min
    retry: 0, // 404 for unheld tickers is expected — don't retry
  });
}

// ── Stock News ──────────────────────────────────────────────────────────────

export function useStockNews(ticker: string, enabled = true) {
  return useQuery({
    queryKey: ["stock-news", ticker],
    queryFn: () => get<StockNewsResponse>(`/stocks/${ticker}/news`),
    staleTime: 5 * 60 * 1000,
    retry: 1,
    enabled,
  });
}

// ── Stock Intelligence ──────────────────────────────────────────────────────

export function useStockIntelligence(ticker: string, enabled = true) {
  return useQuery({
    queryKey: ["stock-intelligence", ticker],
    queryFn: () =>
      get<StockIntelligenceResponse>(`/stocks/${ticker}/intelligence`),
    staleTime: 5 * 60 * 1000,
    retry: 1,
    enabled,
  });
}

// ── Benchmark Comparison ────────────────────────────────────────────────────

export interface BenchmarkDataPoint {
  date: string;
  [seriesName: string]: string | number;
}

export function useBenchmark(
  ticker: string,
  period: PricePeriod,
  enabled = true
) {
  return useQuery({
    queryKey: ["benchmark", ticker, period],
    queryFn: () =>
      get<BenchmarkComparisonResponse>(
        `/stocks/${ticker}/benchmark?period=${period}`
      ),
    staleTime: 5 * 60 * 1000,
    retry: 1,
    enabled,
    select: (data): BenchmarkDataPoint[] => {
      if (!data.series.length) return [];

      const stockSeries = data.series.find(
        (s) => s.ticker.toUpperCase() === ticker.toUpperCase()
      );
      if (!stockSeries) return [];

      const seriesMaps = data.series.map((s) => {
        const map = new Map<string, number>();
        s.dates.forEach((d, i) => {
          const dateKey = d.split("T")[0];
          map.set(dateKey, s.pct_change[i]);
        });
        return { name: s.name, map };
      });

      return stockSeries.dates.map((d) => {
        const dateKey = d.split("T")[0];
        const point: BenchmarkDataPoint = { date: dateKey };
        for (const { name, map } of seriesMaps) {
          const val = map.get(dateKey);
          if (val !== undefined) point[name] = val;
        }
        return point;
      });
    },
  });
}

// ── OHLC (Candlestick) ─────────────────────────────────────────────────────

export function useOHLC(
  ticker: string,
  period: PricePeriod,
  enabled = true
) {
  return useQuery({
    queryKey: ["ohlc", ticker, period],
    queryFn: () =>
      get<OHLCResponse>(
        `/stocks/${ticker}/prices?period=${period}&format=ohlc`
      ),
    staleTime: 5 * 60 * 1000,
    enabled,
  });
}

// ── Preferences ──────────────────────────────────────────────────────────────

export function usePreferences() {
  return useQuery({
    queryKey: ["preferences"],
    queryFn: () => get<UserPreferences>("/preferences"),
    staleTime: 5 * 60 * 1000,
  });
}

export function useUpdatePreferences() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UserPreferencesUpdate) =>
      patch<UserPreferences>("/preferences", body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["preferences"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio"] });
      toast.success("Preferences saved");
    },
    onError: (err) => {
      toast.error(err instanceof Error ? err.message : "Failed to save preferences");
    },
  });
}

export function useRebalancing() {
  return useQuery<RebalancingResponse>({
    queryKey: ["portfolio", "rebalancing"],
    queryFn: () => get<RebalancingResponse>("/portfolio/rebalancing"),
    staleTime: 5 * 60 * 1000, // 5 min
  });
}

// ── Portfolio ─────────────────────────────────────────────────────────────────

export function usePositions() {
  return useQuery<Position[]>({
    queryKey: ["portfolio", "positions"],
    queryFn: () => get<Position[]>("/portfolio/positions"),
    staleTime: 60 * 1000,
  });
}

export function usePortfolioSummary() {
  return useQuery<PortfolioSummary>({
    queryKey: ["portfolio", "summary"],
    queryFn: () => get<PortfolioSummary>("/portfolio/summary"),
    staleTime: 60 * 1000,
  });
}

export function usePortfolioHistory(days = 365) {
  return useQuery<PortfolioSnapshot[]>({
    queryKey: ["portfolio", "history", days],
    queryFn: () => get<PortfolioSnapshot[]>(`/portfolio/history?days=${days}`),
    staleTime: 15 * 60 * 1000,
  });
}

export function useRecommendations() {
  return useQuery<Recommendation[]>({
    queryKey: ["recommendations"],
    queryFn: async () => {
      const resp = await get<PaginatedRecommendations>("/stocks/recommendations");
      return resp.recommendations;
    },
    staleTime: 5 * 60 * 1000,
  });
}

// ── Market Briefing ──────────────────────────────────────────────────────────

export function useMarketBriefing() {
  return useQuery<MarketBriefingResult>({
    queryKey: ["market-briefing"],
    queryFn: () => get<MarketBriefingResult>("/market/briefing"),
    staleTime: 5 * 60 * 1000,
  });
}

// ── Portfolio Health ─────────────────────────────────────────────────────────

export function usePortfolioHealth() {
  return useQuery<PortfolioHealthResult>({
    queryKey: ["portfolio-health"],
    queryFn: () => get<PortfolioHealthResult>("/portfolio/health"),
    staleTime: 5 * 60 * 1000,
  });
}

export function usePortfolioHealthHistory(days: number = 7) {
  return useQuery<PortfolioHealthResult[]>({
    queryKey: ["portfolio-health-history", days],
    queryFn: () =>
      get<PortfolioHealthResult[]>(`/portfolio/health/history?days=${days}`),
    staleTime: 5 * 60 * 1000,
  });
}

// ── Dashboard News ───────────────────────────────────────────────────────────

export function useUserDashboardNews(enabled: boolean = true) {
  return useQuery<DashboardNewsResponse>({
    queryKey: ["dashboard-news"],
    queryFn: () => get<DashboardNewsResponse>("/news/dashboard"),
    staleTime: 5 * 60 * 1000,
    enabled,
  });
}

// ── Bulk Signals by Tickers ──────────────────────────────────────────────────

export function useBulkSignalsByTickers(
  tickers: string[],
  enabled: boolean = true
) {
  return useQuery<BulkSignalsResponse>({
    queryKey: ["bulk-signals-by-ticker", tickers],
    queryFn: () =>
      get<BulkSignalsResponse>(
        `/stocks/signals/bulk?tickers=${tickers.join(",")}&limit=${tickers.length}`
      ),
    enabled: enabled && tickers.length > 0,
    staleTime: 60 * 1000,
  });
}

// ── Portfolio Analytics (QuantStats) ─────────────────────────────────────────

export function usePortfolioAnalytics() {
  return useQuery<PortfolioAnalyticsResponse>({
    queryKey: ["portfolio", "analytics"],
    queryFn: () => get<PortfolioAnalyticsResponse>("/portfolio/analytics"),
    staleTime: 5 * 60 * 1000,
  });
}

// ── Stock Analytics (QuantStats) ─────────────────────────────────────────────

export function useStockAnalytics(ticker: string) {
  return useQuery<StockAnalyticsResponse>({
    queryKey: ["stock-analytics", ticker],
    queryFn: () => get<StockAnalyticsResponse>(`/stocks/${ticker}/analytics`),
    staleTime: 5 * 60 * 1000,
    enabled: !!ticker,
  });
}
