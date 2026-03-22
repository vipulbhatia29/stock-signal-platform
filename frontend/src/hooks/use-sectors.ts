"use client";

import { useQuery } from "@tanstack/react-query";
import { get } from "@/lib/api";
import type {
  SectorScope,
  SectorSummaryResponse,
  SectorStocksResponse,
  CorrelationData,
} from "@/types/api";

/** Fetch all sectors with summary stats. */
export function useSectors(scope: SectorScope = "all") {
  return useQuery({
    queryKey: ["sectors", scope],
    queryFn: () =>
      get<SectorSummaryResponse>(`/sectors?scope=${scope}`),
    staleTime: 60 * 1000,
  });
}

/** Fetch stocks within a sector. Enabled only when sector is provided. */
export function useSectorStocks(sector: string | null) {
  return useQuery({
    queryKey: ["sector-stocks", sector],
    queryFn: () =>
      get<SectorStocksResponse>(
        `/sectors/${encodeURIComponent(sector!)}/stocks`
      ),
    enabled: !!sector,
    staleTime: 60 * 1000,
  });
}

/** Fetch correlation matrix for tickers in a sector. */
export function useSectorCorrelation(
  sector: string | null,
  tickers: string[] | null,
  periodDays = 90
) {
  const tickerParam = tickers?.join(",") ?? "";
  return useQuery({
    queryKey: ["sector-correlation", sector, tickerParam, periodDays],
    queryFn: () => {
      const params = new URLSearchParams();
      if (tickerParam) params.set("tickers", tickerParam);
      params.set("period_days", String(periodDays));
      return get<CorrelationData>(
        `/sectors/${encodeURIComponent(sector!)}/correlation?${params}`
      );
    },
    enabled: !!sector && (tickers === null || tickers.length >= 2),
    staleTime: 5 * 60 * 1000,
  });
}
