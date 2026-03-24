"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { StarIcon, RefreshCw } from "lucide-react";
import { useChat } from "@/contexts/chat-context";
import {
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
  useRecommendations,
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
import { RecommendationRow } from "@/components/recommendation-row";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import * as api from "@/lib/api";
import { cn } from "@/lib/utils";
import { formatCurrency } from "@/lib/format";
import { usePortfolioForecast, useScorecard } from "@/hooks/use-forecasts";
import { ScorecardModal } from "@/components/scorecard-modal";
import { WelcomeBanner } from "@/components/welcome-banner";
import { TrendingStocks } from "@/components/trending-stocks";
import { PageTransition, StaggerGroup, StaggerItem } from "@/components/motion-primitives";

export default function DashboardPage() {
  const [sectorFilter, setSectorFilter] = useState<string | null>(null);

  const queryClient = useQueryClient();
  const { chatOpen: chatIsOpen } = useChat();

  const [addingTickers, setAddingTickers] = useState<Set<string>>(new Set());
  const { data: indexes, isLoading: indexesLoading } = useIndexes();
  const { data: watchlist, isLoading: watchlistLoading } = useWatchlist();
  const { data: recommendations } = useRecommendations();
  const { data: portfolioForecast } = usePortfolioForecast();
  const { data: scorecard } = useScorecard();
  const addToWatchlist = useAddToWatchlist();
  const removeFromWatchlist = useRemoveFromWatchlist();

  // ── Refresh All — direct ingest (no Celery dependency) ─────────────────────

  const [refreshingAll, setRefreshingAll] = useState(false);

  const refreshAllMutation = useMutation({
    mutationFn: async () => {
      if (!watchlist?.length) return;
      setRefreshingAll(true);
      let succeeded = 0;
      let failed = 0;
      for (const item of watchlist) {
        try {
          await api.post(`/stocks/${item.ticker}/ingest`);
          succeeded++;
        } catch {
          failed++;
        }
      }
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
      queryClient.invalidateQueries({ queryKey: ["trending-stocks"] });
      if (failed === 0) {
        toast.success(`Refreshed ${succeeded} stock${succeeded !== 1 ? "s" : ""}`);
      } else {
        toast.warning(`Refreshed ${succeeded}, failed ${failed}`);
      }
      setRefreshingAll(false);
    },
  });

  // ── Acknowledge stale price mutation ────────────────────────────────────────

  const acknowledgeMutation = useMutation({
    mutationFn: (ticker: string) =>
      api.post(`/stocks/watchlist/${ticker}/acknowledge`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["watchlist"] }),
  });

  // ── Portfolio overview ──────────────────────────────────────────────────────

  const router = useRouter();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const { data: summary } = usePortfolioSummary();
  const { data: positions } = usePositions();

  const heldTickers = useMemo(() => {
    if (!positions) return new Set<string>();
    return new Set(positions.map((p) => p.ticker));
  }, [positions]);

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
        // Matches backend: BUY >= 8, WATCH >= 5, AVOID < 5
        const score = w.composite_score ?? 0;
        if (score >= 8) acc.buy++;
        else if (score >= 5) acc.hold++;
        else acc.sell++;
        return acc;
      },
      { buy: 0, hold: 0, sell: 0 }
    );
  }, [watchlist]);

  const topSignal = useMemo(() => {
    if (!watchlist || watchlist.length === 0) return null;
    // Pick the highest-scoring watchlist stock (regardless of threshold)
    return (
      [...watchlist]
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
      await api.post(`/stocks/${ticker}/ingest`);
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

  // Helper to generate reasoning text from recommendation data
  const getReasoningText = (rec: { action: string; confidence: string; composite_score: number; reasoning?: Record<string, unknown> | null }): string => {
    if (rec.reasoning && typeof rec.reasoning === "object" && "summary" in rec.reasoning) {
      return String(rec.reasoning.summary);
    }
    // Template-based fallback
    // composite_score is already 0-10 from API
    const score = rec.composite_score.toFixed(1);
    if (rec.action === "BUY") return `Strong signals with composite score ${score}. Consider adding to portfolio.`;
    if (rec.action === "WATCH") return `Mixed signals — composite score ${score}. Monitor for entry point.`;
    if (rec.action === "AVOID") return `Weak signals with composite score ${score}. High risk indicators.`;
    if (rec.action === "SELL") return `Bearish across indicators. Score ${score}. Consider reducing exposure.`;
    return `Composite score ${score}. Hold current position.`;
  };

  return (
    <PageTransition className="space-y-6">
      {/* Welcome Banner (new users) */}
      <WelcomeBanner onAddTicker={handleQuickAdd} addingTickers={addingTickers} />

      {/* Trending Stocks (visible even with empty watchlist) */}
      <TrendingStocks />

      {/* KPI Stat Tiles — organized into portfolio + signals groups */}
      <section>
        <SectionHeading>Overview</SectionHeading>
        <StaggerGroup className={cn(
          "grid grid-cols-2 gap-3 transition-all duration-300",
          chatIsOpen ? "lg:grid-cols-3 xl:grid-cols-5" : "lg:grid-cols-5"
        )}>
          {/* Portfolio Value */}
          <StaggerItem>
            <StatTile
              label="Portfolio Value"
              value={summary ? formatCurrency(summary.total_value) : "—"}
              sub={
                summary?.unrealized_pnl != null ? (
                  <ChangeIndicator value={summary.unrealized_pnl} format="currency" size="sm" showIcon={false} prefix="$" />
                ) : undefined
              }
              accentColor="cyan"
              onClick={() => setDrawerOpen(true)}
            />
          </StaggerItem>

          {/* Unrealized P&L */}
          <StaggerItem>
            <StatTile
              label="Unrealized P&L"
              value={summary ? formatCurrency(summary.unrealized_pnl) : "—"}
              sub={
                summary?.unrealized_pnl_pct != null ? (
                  <ChangeIndicator value={summary.unrealized_pnl_pct} format="percent" size="sm" showIcon={false} />
                ) : undefined
              }
              accentColor={
                (summary?.unrealized_pnl ?? 0) >= 0 ? "gain" : "loss"
              }
            />
          </StaggerItem>

          {/* Signals */}
          <StaggerItem>
          <StatTile label="Signals" accentColor="warn">
            <div className="grid grid-cols-3 gap-[5px] mt-[7px]">
              <div className="text-center rounded-[6px] py-[7px] bg-[var(--gdim)]">
                <div className="font-mono text-[20px] font-bold leading-none text-gain">{signalCounts.buy}</div>
                <div className="text-[9px] font-semibold tracking-[0.07em] uppercase mt-0.5 text-gain">Buy</div>
              </div>
              <div className="text-center rounded-[6px] py-[7px] bg-[var(--wdim)]">
                <div className="font-mono text-[20px] font-bold leading-none text-warning">{signalCounts.hold}</div>
                <div className="text-[9px] font-semibold tracking-[0.07em] uppercase mt-0.5 text-warning">Watch</div>
              </div>
              <div className="text-center rounded-[6px] py-[7px] bg-[var(--ldim)]">
                <div className="font-mono text-[20px] font-bold leading-none text-loss">{signalCounts.sell}</div>
                <div className="text-[9px] font-semibold tracking-[0.07em] uppercase mt-0.5 text-loss">Avoid</div>
              </div>
            </div>
          </StatTile>
          </StaggerItem>

          {/* Top Signal */}
          <StaggerItem>
          <StatTile label="Top Signal" accentColor={
            (topSignal?.composite_score ?? 0) >= 8 ? "gain" : (topSignal?.composite_score ?? 0) >= 5 ? "warn" : "loss"
          }>
            {topSignal ? (
              <div className="mt-1">
                <div className="font-mono text-[18px] font-bold text-foreground">{topSignal.ticker}</div>
                <div className="text-[10px] text-muted-foreground truncate">{topSignal.name}</div>
                <div className="flex items-center gap-1.5 mt-1.5">
                  {(() => {
                    const s = topSignal.composite_score ?? 0;
                    const label = s >= 8 ? "BUY" : s >= 5 ? "WATCH" : "AVOID";
                    const cls = s >= 8 ? "bg-gain/10 text-gain" : s >= 5 ? "bg-warning/10 text-warning" : "bg-loss/10 text-loss";
                    return <span className={`inline-flex items-center rounded px-1 py-0.5 text-[9px] font-semibold ${cls}`}>{label}</span>;
                  })()}
                  <span className="font-mono text-[11px] text-muted-foreground">
                    {(topSignal.composite_score ?? 0).toFixed(1)}/10
                  </span>
                </div>
              </div>
            ) : (
              <div className="text-[10px] text-muted-foreground mt-2">No strong signals</div>
            )}
          </StatTile>
          </StaggerItem>

          {/* Allocation */}
          <StaggerItem>
            <StatTile label="Allocation" accentColor="cyan" onClick={() => router.push("/sectors")}>
              <AllocationDonut
                allocations={allocations}
                stockCount={positions?.length}
                showSectorLink
              />
            </StatTile>
          </StaggerItem>

          {/* Portfolio Outlook */}
          <StaggerItem>
            <StatTile
              label="Portfolio Outlook"
              accentColor="cyan"
              value={
                portfolioForecast?.horizons?.[0]
                  ? `${portfolioForecast.horizons[0].expected_return_pct >= 0 ? "+" : ""}${portfolioForecast.horizons[0].expected_return_pct.toFixed(1)}%`
                  : "—"
              }
              sub={
                portfolioForecast?.horizons?.[0] ? (
                  <span className="text-[9px] text-subtle">
                    90d · {portfolioForecast.ticker_count} stocks
                  </span>
                ) : (
                  <span className="text-[9px] text-subtle">No forecast data</span>
                )
              }
            />
          </StaggerItem>

          {/* Accuracy — click opens scorecard modal */}
          <StaggerItem>
            <ScorecardModal>
              <StatTile
                label="Accuracy"
                accentColor={
                  (scorecard?.overall_hit_rate ?? 0) >= 0.7 ? "gain" : "warn"
                }
                value={
                  scorecard?.total_outcomes
                    ? `${(scorecard.overall_hit_rate * 100).toFixed(0)}%`
                    : "—"
                }
                sub={
                  scorecard?.total_outcomes ? (
                    <span className="text-[9px] text-subtle">
                      {scorecard.total_outcomes} recs · {(scorecard.avg_alpha * 100).toFixed(1)}% alpha
                    </span>
                  ) : (
                    <span className="text-[9px] text-subtle">No outcomes yet</span>
                  )
                }
              />
            </ScorecardModal>
          </StaggerItem>
        </StaggerGroup>
      </section>

      {/* Market Indexes — 3-col, adapts with chat */}
      <section>
        <SectionHeading>Market Indexes</SectionHeading>
        {indexesLoading ? (
          <div className={cn(
            "grid grid-cols-1 gap-3 transition-all duration-300",
            chatIsOpen ? "md:grid-cols-2 xl:grid-cols-3" : "md:grid-cols-3"
          )}>
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
          <div className={cn(
            "grid grid-cols-1 gap-3 transition-all duration-300",
            chatIsOpen ? "md:grid-cols-2 xl:grid-cols-3" : "md:grid-cols-3"
          )}>
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

      {/* Action Required — only for portfolio-held stocks */}
      {(() => {
        const portfolioRecs = recommendations?.filter((rec) => heldTickers.has(rec.ticker)) ?? [];
        return portfolioRecs.length > 0 ? (
        <section>
          <SectionHeading>Action Required</SectionHeading>
          <div className="space-y-2">
            {portfolioRecs.slice(0, 5).map((rec) => (
              <RecommendationRow
                key={rec.ticker}
                ticker={rec.ticker}
                action={rec.action}
                confidence={rec.confidence}
                compositeScore={rec.composite_score}
                reasoning={getReasoningText(rec)}
                isHeld={heldTickers.has(rec.ticker)}
              />
            ))}
          </div>
        </section>
        ) : null;
      })()}

      {/* Portfolio Drawer */}
      <PortfolioDrawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      />

      {/* Watchlist — 4-col, 3-col when chat open */}
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
                disabled={refreshAllMutation.isPending || refreshingAll}
              >
                <RefreshCw
                  className={cn(
                    "h-4 w-4 mr-1.5",
                    refreshingAll && "animate-spin"
                  )}
                />
                {refreshingAll ? "Refreshing…" : "Refresh All"}
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
          <div className={cn(
            "grid grid-cols-1 gap-3 transition-all duration-300",
            chatIsOpen ? "sm:grid-cols-2 lg:grid-cols-3" : "sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
          )}>
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
          <div className={cn(
            "grid grid-cols-1 gap-3 transition-all duration-300",
            chatIsOpen ? "sm:grid-cols-2 lg:grid-cols-3" : "sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
          )}>
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
                isRefreshing={refreshingAll}
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
    </PageTransition>
  );
}
