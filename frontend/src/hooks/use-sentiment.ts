"use client";

import { useQuery } from "@tanstack/react-query";
import { get } from "@/lib/api";
import type {
  SentimentTimeseriesResponse,
  ArticleListResponse,
  BulkSentimentResponse,
} from "@/types/api";

/** Fetch daily sentiment timeseries for a single ticker. */
export function useSentiment(ticker: string | null, days = 30) {
  return useQuery({
    queryKey: ["sentiment", ticker, days],
    queryFn: () =>
      get<SentimentTimeseriesResponse>(
        `/sentiment/${ticker}?days=${days}`,
      ),
    enabled: !!ticker,
    staleTime: 30 * 60 * 1000,
  });
}

/** Fetch bulk sentiment for a list of tickers. */
export function useBulkSentiment(tickers: string[], enabled = true) {
  const tickerParam = tickers.join(",");
  return useQuery({
    queryKey: ["sentiment", "bulk", tickerParam],
    queryFn: () => get<BulkSentimentResponse>(`/sentiment/bulk?tickers=${tickerParam}`),
    staleTime: 30 * 60 * 1000,
    enabled: enabled && tickers.length > 0,
  });
}

/** Fetch macro-level sentiment timeseries. */
export function useMacroSentiment(days = 30) {
  return useQuery({
    queryKey: ["sentiment", "macro", days],
    queryFn: () =>
      get<SentimentTimeseriesResponse>(
        `/sentiment/macro?days=${days}`,
      ),
    staleTime: 30 * 60 * 1000,
  });
}

/** Fetch paginated news articles for a single ticker. */
export function useTickerArticles(ticker: string | null, days = 30) {
  return useQuery({
    queryKey: ["sentiment-articles", ticker, days],
    queryFn: () =>
      get<ArticleListResponse>(
        `/sentiment/${ticker}/articles?days=${days}`,
      ),
    enabled: !!ticker,
    staleTime: 30 * 60 * 1000,
  });
}
