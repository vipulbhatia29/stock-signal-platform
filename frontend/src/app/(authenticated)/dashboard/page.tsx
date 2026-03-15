"use client";

import { useEffect, useMemo, useState } from "react";
import { StarIcon, RefreshCw } from "lucide-react";
import {
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import {
  useIndexes,
  useWatchlist,
  useRemoveFromWatchlist,
} from "@/hooks/use-stocks";
import { IndexCard, IndexCardSkeleton } from "@/components/index-card";
import { StockCard, StockCardSkeleton } from "@/components/stock-card";
import { SectorFilter } from "@/components/sector-filter";
import { EmptyState } from "@/components/empty-state";
import { SectionHeading } from "@/components/section-heading";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import * as api from "@/lib/api";
import type { TaskStatus, RefreshTask } from "@/types/api";
import { cn } from "@/lib/utils";

export default function DashboardPage() {
  const [sectorFilter, setSectorFilter] = useState<string | null>(null);
  const [refreshTasks, setRefreshTasks] = useState<Record<string, string>>({});

  const queryClient = useQueryClient();

  const { data: indexes, isLoading: indexesLoading } = useIndexes();
  const { data: watchlist, isLoading: watchlistLoading } = useWatchlist();
  const removeFromWatchlist = useRemoveFromWatchlist();

  // ── Refresh All mutation ────────────────────────────────────────────────────

  const refreshAllMutation = useMutation({
    mutationFn: () =>
      api.post<RefreshTask[]>("/stocks/watchlist/refresh-all"),
  });

  // ── Acknowledge stale price mutation ────────────────────────────────────────

  const acknowledgeMutation = useMutation({
    mutationFn: (ticker: string) =>
      api.post(`/stocks/watchlist/${ticker}/acknowledge`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["watchlist"] }),
  });

  // When refresh-all succeeds, populate the task map
  useEffect(() => {
    if (refreshAllMutation.data) {
      const taskMap: Record<string, string> = {};
      refreshAllMutation.data.forEach((t) => {
        taskMap[t.ticker] = t.task_id;
      });
      setTimeout(() => setRefreshTasks(taskMap), 0);
    }
  }, [refreshAllMutation.data]);

  // ── Per-task polling ────────────────────────────────────────────────────────

  const hasInFlightTasks = Object.keys(refreshTasks).length > 0;

  const taskPollQuery = useQuery({
    queryKey: ["task-poll", refreshTasks],
    queryFn: async () => {
      const results = await Promise.all(
        Object.entries(refreshTasks).map(async ([ticker, taskId]) => {
          const res = await api.get<TaskStatus>(
            `/tasks/${taskId}/status`
          );
          return { ticker, taskId, state: res.state };
        })
      );
      return results;
    },
    enabled: hasInFlightTasks,
    refetchInterval: hasInFlightTasks ? 2000 : false,
  });

  // Process completed tasks
  useEffect(() => {
    if (!taskPollQuery.data) return;
    const stillPending: Record<string, string> = {};
    taskPollQuery.data.forEach(({ ticker, taskId, state }) => {
      if (state === "SUCCESS") {
        queryClient.invalidateQueries({ queryKey: ["watchlist"] });
      } else if (state === "FAILURE") {
        toast.error(
          `Couldn't refresh ${ticker} — Yahoo Finance may be rate limited. Try again in a few minutes.`
        );
      } else {
        stillPending[ticker] = taskId;
      }
    });
    setTimeout(() => setRefreshTasks(stillPending), 0);
  }, [taskPollQuery.data, queryClient]);

  // ── Derived data ────────────────────────────────────────────────────────────

  const sectors = useMemo(() => {
    if (!watchlist) return [];
    const unique = new Set(watchlist.map((w) => w.sector).filter(Boolean));
    return Array.from(unique).sort() as string[];
  }, [watchlist]);

  const filteredWatchlist = useMemo(() => {
    if (!watchlist) return [];
    if (!sectorFilter) return watchlist;
    return watchlist.filter((w) => w.sector === sectorFilter);
  }, [watchlist, sectorFilter]);

  return (
    <div className="space-y-8">
      {/* Index Cards */}
      <section>
        <SectionHeading>Market Indexes</SectionHeading>
        {indexesLoading ? (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <IndexCardSkeleton key={i} />
            ))}
          </div>
        ) : !indexes?.length ? (
          <p className="text-sm text-muted-foreground">
            No indexes seeded yet. Run{" "}
            <code className="font-mono text-xs">
              uv run python scripts/sync_indexes.py
            </code>{" "}
            to populate.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {indexes.map((idx, i) => (
              <IndexCard
                key={idx.slug}
                name={idx.name}
                slug={idx.slug}
                stockCount={idx.stock_count}
                description={idx.description}
                animationDelay={i * 80}
              />
            ))}
          </div>
        )}
      </section>

      {/* Watchlist */}
      <section>
        <SectionHeading
          action={
            <div className="flex items-center gap-2">
              {sectors.length > 1 && (
                <SectorFilter
                  sectors={sectors}
                  selected={sectorFilter}
                  onChange={setSectorFilter}
                />
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={() => refreshAllMutation.mutate()}
                disabled={refreshAllMutation.isPending || hasInFlightTasks}
              >
                <RefreshCw
                  className={cn(
                    "h-4 w-4 mr-1.5",
                    hasInFlightTasks && "animate-spin"
                  )}
                />
                Refresh All
              </Button>
            </div>
          }
        >
          Watchlist
          {filteredWatchlist.length > 0 && (
            <span className="ml-2 font-normal normal-case text-foreground tracking-normal">
              ({filteredWatchlist.length})
            </span>
          )}
        </SectionHeading>

        {watchlistLoading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <StockCardSkeleton key={i} />
            ))}
          </div>
        ) : filteredWatchlist.length === 0 ? (
          <EmptyState
            icon={StarIcon}
            title="No stocks in your watchlist"
            description="Search for a ticker above to start tracking stocks"
          />
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {filteredWatchlist.map((item, i) => (
              <StockCard
                key={item.ticker}
                ticker={item.ticker}
                name={item.name}
                sector={item.sector}
                score={item.composite_score}
                onRemove={() => removeFromWatchlist.mutate(item.ticker)}
                animationDelay={Math.min(i, 7) * 60}
                currentPrice={item.current_price}
                priceUpdatedAt={item.price_updated_at}
                priceAcknowledgedAt={item.price_acknowledged_at}
                isRefreshing={item.ticker in refreshTasks}
                onRefresh={async (ticker) => {
                  await api.post(`/stocks/${ticker}/ingest`);
                  queryClient.invalidateQueries({ queryKey: ["watchlist"] });
                }}
                onAcknowledge={(ticker) => acknowledgeMutation.mutate(ticker)}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
