import { useQuery } from "@tanstack/react-query";
import { get } from "@/lib/api";
import type { IngestState } from "@/types/api";

/**
 * Poll the backend ingest-state endpoint every 2s while status is "ingesting".
 * Stops polling once overall_status === "ready".
 */
export function useIngestProgress(ticker: string | null, enabled: boolean) {
  return useQuery<IngestState>({
    queryKey: ["ingest-state", ticker],
    queryFn: () => get<IngestState>(`/stocks/${ticker}/ingest-state`),
    enabled: enabled && !!ticker,
    refetchInterval: (q) => {
      const data = q.state.data;
      if (!data) return 2000;
      if (data.overall_status === "ready") return false;
      return 2000;
    },
    staleTime: 0,
  });
}
