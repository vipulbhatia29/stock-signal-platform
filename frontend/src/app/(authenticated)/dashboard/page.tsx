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
  useAddToWatchlist,
  useRemoveFromWatchlist,
  usePortfolioSummary,
  usePositions,
} from "@/hooks/use-stocks";
import { IndexCard, IndexCardSkeleton } from "@/components/index-card";
import { StockCard, StockCardSkeleton } from "@/components/stock-card";
import { SectorFilter } from "@/components/sector-filter";
import { EmptyState } from "@/components/empty-state";
import { SectionHeading } from "@/components/section-heading";
import { StatTile } from "@/components/stat-tile";
import { AllocationDonut, DONUT_COLORS } from "@/components/allocation-donut";
import { PortfolioDrawer } from "@/components/portfolio-drawer";
import { ChangeIndicator } from "@/components/change-indicator";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import * as api from "@/lib/api";
import type { TaskStatus, RefreshTask } from "@/types/api";
import { cn } from "@/lib/utils";
import { formatCurrency } from "@/lib/format";
import { WelcomeBanner } from "@/components/welcome-banner";
import { TrendingStocks } from "@/components/trending-stocks";

export default function DashboardPage() {
  const [sectorFilter, setSectorFilter] = useState<string | null>(null);
  const [refreshTasks, setRefreshTasks] = useState<Record<string, string>>({});

  const queryClient = useQueryClient();

  const [addingTickers, setAddingTickers] = useState<Set<string>>(new Set());
  const { data: indexes, isLoading: indexesLoading } = useIndexes();
  const { data: watchlist, isLoading: watchlistLoading } = useWatchlist();
  const addToWatchlist = useAddToWatchlist();
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

  // ── Portfolio overview ──────────────────────────────────────────────────────

  const [drawerOpen, setDrawerOpen] = useState(false);
  const chatIsOpen = false; // TODO: wire from layout context

  const { data: summary } = usePortfolioSummary();
  const { data: positions } = usePositions();

  const allocations = useMemo(() => {
    if (!positions) return [];
    const sectorTotals: Record<string, number> = {};
    let total = 0;
    positions.forEach((p) => {
      const sector = p.sector ?? "Other";
      sectorTotals[sector] = (sectorTotals[sector] ?? 0) + (p.market_value ?? 0);
      total += p.market_value ?? 0;
    });
    return Object.entries(sectorTotals).map(([sector, value], i) => ({
      sector,
      pct: total > 0 ? (value / total) * 100 : 0,
      color: DONUT_COLORS[i % DONUT_COLORS.length],
    }));
  }, [positions]);

  const signalCounts = useMemo(() => {
    if (!watchlist) return { buy: 0, hold: 0, sell: 0 };
    return watchlist.reduce(
      (acc, w) => {
        const score = w.composite_score ?? 0;
        if (score >= 0.6) acc.buy++;
        else if (score >= 0.4) acc.hold++;
        else acc.sell++;
        return acc;
      },
      { buy: 0, hold: 0, sell: 0 }
    );
  }, [watchlist]);

  const topSignal = useMemo(() => {
    if (!watchlist) return null;
    return (
      watchlist
        .filter((w) => (w.composite_score ?? 0) >= 0.6)
        .sort((a, b) => (b.composite_score ?? 0) - (a.composite_score ?? 0))[0] ?? null
    );
  }, [watchlist]);

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

  const handleQuickAdd = async (ticker: string) => {
    setAddingTickers((prev) => new Set(prev).add(ticker));
    try {
      // Ingest first (ensures stock exists with fresh data)
      await api.post(`/stocks/${ticker}/ingest`);
      // Then add to watchlist
      addToWatchlist.mutate(ticker);
    } catch {
      toast.error(`Failed to add ${ticker}`);
    } finally {
      setAddingTickers((prev) => {
        const next = new Set(prev);
        next.delete(ticker);
        return next;
      });
    }
  };

  return (
    <div className="space-y-8">
      {/* Welcome Banner (new users) */}
      <WelcomeBanner onAddTicker={handleQuickAdd} addingTickers={addingTickers} />

      {/* Trending Stocks (visible even with empty watchlist) */}
      <TrendingStocks />

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

      {/* Overview tiles */}
      <section>
        <SectionHeading>Overview</SectionHeading>
        <div className="grid grid-cols-5 gap-[9px]">
          {/* Portfolio Value */}
          <StatTile
            label="Portfolio Value"
            value={summary ? formatCurrency(summary.total_value) : "—"}
            sub={
              summary?.unrealized_pnl != null ? (
                <ChangeIndicator value={summary.unrealized_pnl} format="currency" />
              ) : undefined
            }
            accentColor="cyan"
            onClick={() => setDrawerOpen(true)}
          />

          {/* Unrealized P&L */}
          <StatTile
            label="Unrealized P&L"
            value={summary ? formatCurrency(summary.unrealized_pnl) : "—"}
            sub={
              summary?.unrealized_pnl_pct != null ? (
                <ChangeIndicator value={summary.unrealized_pnl_pct} format="percent" />
              ) : undefined
            }
            accentColor={
              (summary?.unrealized_pnl ?? 0) >= 0 ? "gain" : "loss"
            }
          />

          {/* Signals */}
          <StatTile label="Signals" accentColor="warn">
            <div className="grid grid-cols-3 gap-[5px] mt-[7px]">
              <div className="text-center rounded-[6px] py-[7px] bg-[var(--gdim)]">
                <div className="font-mono text-[20px] font-bold leading-none text-gain">{signalCounts.buy}</div>
                <div className="text-[9px] font-semibold tracking-[0.07em] uppercase mt-0.5 text-gain">Buy</div>
              </div>
              <div className="text-center rounded-[6px] py-[7px] bg-[var(--wdim)]">
                <div className="font-mono text-[20px] font-bold leading-none text-warning">{signalCounts.hold}</div>
                <div className="text-[9px] font-semibold tracking-[0.07em] uppercase mt-0.5 text-warning">Hold</div>
              </div>
              <div className="text-center rounded-[6px] py-[7px] bg-[var(--ldim)]">
                <div className="font-mono text-[20px] font-bold leading-none text-loss">{signalCounts.sell}</div>
                <div className="text-[9px] font-semibold tracking-[0.07em] uppercase mt-0.5 text-loss">Sell</div>
              </div>
            </div>
          </StatTile>

          {/* Top Signal */}
          <StatTile label="Top Signal" accentColor="gain">
            {topSignal ? (
              <div className="mt-1">
                <div className="font-mono text-[18px] font-bold text-foreground">{topSignal.ticker}</div>
                <div className="text-[10px] text-subtle truncate">{topSignal.name}</div>
                <div className="font-mono text-[11px] text-gain mt-1">
                  Score: {Math.round((topSignal.composite_score ?? 0) * 100)}
                </div>
              </div>
            ) : (
              <div className="text-[10px] text-subtle mt-2">No strong signals</div>
            )}
          </StatTile>

          {/* Allocation */}
          <StatTile label="Allocation" accentColor="cyan">
            <AllocationDonut
              allocations={allocations}
              stockCount={positions?.length}
            />
          </StatTile>
        </div>
      </section>

      {/* Portfolio Drawer */}
      <PortfolioDrawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        chatIsOpen={chatIsOpen}
      />

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
            description="Search for a ticker above, or add a popular stock to get started"
            action={
              <div className="flex flex-wrap justify-center gap-2">
                {["AAPL", "MSFT", "GOOGL", "NVDA", "TSLA"].map((ticker) => (
                  <Button
                    key={ticker}
                    variant="outline"
                    size="sm"
                    onClick={() => handleQuickAdd(ticker)}
                    disabled={addingTickers.has(ticker)}
                  >
                    + {ticker}
                  </Button>
                ))}
              </div>
            }
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
