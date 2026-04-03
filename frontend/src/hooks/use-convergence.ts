"use client";

import { useQuery } from "@tanstack/react-query";
import { get } from "@/lib/api";
import type {
  ConvergenceResponse,
  PortfolioConvergenceResponse,
  ConvergenceHistoryResponse,
  SectorConvergenceResponse,
} from "@/types/api";

/** Query key factory for convergence data. */
export const convergenceKeys = {
  all: ["convergence"] as const,
  ticker: (ticker: string) => [...convergenceKeys.all, ticker] as const,
  portfolio: (id: string) =>
    [...convergenceKeys.all, "portfolio", id] as const,
  history: (ticker: string) =>
    [...convergenceKeys.all, "history", ticker] as const,
  sector: (sector: string) =>
    [...convergenceKeys.all, "sector", sector] as const,
};

/** Fetch convergence for a single ticker (traffic lights + rationale). */
export function useStockConvergence(ticker: string | null) {
  return useQuery({
    queryKey: convergenceKeys.ticker(ticker ?? ""),
    queryFn: () => get<ConvergenceResponse>(`/convergence/${ticker}`),
    enabled: !!ticker,
    staleTime: 30 * 60 * 1000, // 30 min — convergence updates nightly
  });
}

/** Fetch portfolio convergence summary. */
export function usePortfolioConvergence(
  portfolioId: string | null,
  enabled = true,
) {
  return useQuery({
    queryKey: convergenceKeys.portfolio(portfolioId ?? ""),
    queryFn: () =>
      get<PortfolioConvergenceResponse>(
        `/convergence/portfolio/${portfolioId}`,
      ),
    enabled: enabled && !!portfolioId,
    staleTime: 30 * 60 * 1000,
  });
}

/** Fetch convergence history for a ticker. */
export function useConvergenceHistory(
  ticker: string | null,
  days = 90,
  enabled = true,
) {
  return useQuery({
    queryKey: [...convergenceKeys.history(ticker ?? ""), days],
    queryFn: () =>
      get<ConvergenceHistoryResponse>(
        `/convergence/${ticker}/history?days=${days}`,
      ),
    enabled: enabled && !!ticker,
    staleTime: 30 * 60 * 1000,
  });
}

/** Fetch sector convergence summary. */
export function useSectorConvergence(
  sector: string | null,
  enabled = true,
) {
  return useQuery({
    queryKey: convergenceKeys.sector(sector ?? ""),
    queryFn: () =>
      get<SectorConvergenceResponse>(
        `/sectors/${encodeURIComponent(sector!)}/convergence`,
      ),
    enabled: enabled && !!sector,
    staleTime: 30 * 60 * 1000,
  });
}
