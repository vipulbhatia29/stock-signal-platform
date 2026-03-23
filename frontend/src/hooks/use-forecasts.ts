"use client";

import { useQuery } from "@tanstack/react-query";
import { get } from "@/lib/api";
import type {
  ForecastResponse,
  PortfolioForecastResponse,
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

/** Fetch aggregated portfolio forecast. */
export function usePortfolioForecast() {
  return useQuery({
    queryKey: ["portfolio-forecast"],
    queryFn: () => get<PortfolioForecastResponse>("/forecasts/portfolio"),
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
