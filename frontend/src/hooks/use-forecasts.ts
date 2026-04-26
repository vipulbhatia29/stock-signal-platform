"use client";

import { useQuery } from "@tanstack/react-query";
import { get } from "@/lib/api";
import type {
  ForecastResponse,
  ForecastTrackRecordResponse,
  PortfolioForecastFullResponse,
  ScorecardResponse,
} from "@/types/api";

/** Fetch forecast for a single ticker. */
export function useForecast(ticker: string | null) {
  return useQuery({
    queryKey: ["forecast", ticker],
    queryFn: () => get<ForecastResponse>(`/forecasts/${ticker}`),
    enabled: !!ticker,
    staleTime: 30 * 60 * 1000, // 30 min — forecasts update nightly
  });
}

/** Fetch full portfolio forecast (BL + Monte Carlo + CVaR). */
export function usePortfolioForecastFull(portfolioId: string | null) {
  return useQuery({
    queryKey: ["portfolio-forecast-full", portfolioId],
    queryFn: () =>
      get<PortfolioForecastFullResponse>(
        `/portfolio/${portfolioId}/forecast`,
      ),
    enabled: !!portfolioId,
    staleTime: 30 * 60 * 1000,
  });
}

/** Fetch forecast track record — predicted vs actual outcomes. */
export function useForecastTrackRecord(ticker: string | null, days = 365) {
  return useQuery({
    queryKey: ["forecast-track-record", ticker, days],
    queryFn: () =>
      get<ForecastTrackRecordResponse>(
        `/forecasts/${ticker}/track-record?days=${days}`,
      ),
    enabled: !!ticker,
    staleTime: 30 * 60 * 1000,
  });
}

/** Fetch recommendation scorecard. */
export function useScorecard() {
  return useQuery({
    queryKey: ["scorecard"],
    queryFn: () => get<ScorecardResponse>("/recommendations/scorecard"),
    staleTime: 30 * 60 * 1000,
  });
}
