"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { PageTransition } from "@/components/motion-primitives";
import { MigrationToast } from "@/components/migration-toast";
import { WelcomeBanner } from "@/components/welcome-banner";
import { AllocationDonut } from "@/components/allocation-donut";
import { useWatchlist, usePositions, useAddToWatchlist, useMarketBriefing } from "@/hooks/use-stocks";
import { KPIRow } from "./_components/kpi-row";
import { MarketPulseZone } from "./_components/market-pulse-zone";
import { ActionRequiredZone } from "./_components/action-required-zone";
import { TopMoversZone } from "./_components/top-movers-zone";
import { BulletinZone } from "./_components/bulletin-zone";
import { AlertsZone } from "./_components/alerts-zone";
import { NewsZone } from "./_components/news-zone";

const DONUT_COLORS = ["#38bdf8", "#fbbf24", "#a78bfa", "#22d3a0", "#f87171", "#fb923c"];

/**
 * Dashboard — tells the story:
 *   Your money → Market context → What to do → What you're tracking → News & Alerts
 */
export default function DashboardPage() {
  const { data: watchlist = [], isLoading: watchlistLoading } = useWatchlist();
  const { data: positions = [], isLoading: positionsLoading } = usePositions();
  const { data: briefing } = useMarketBriefing();
  const addToWatchlist = useAddToWatchlist();
  const [addingTickers, setAddingTickers] = useState<Set<string>>(new Set());

  const isEmpty =
    !watchlistLoading && !positionsLoading &&
    watchlist.length === 0 && positions.length === 0;

  // Portfolio allocation from actual positions (where your money is)
  const allocations = useMemo(() => {
    if (!positions.length) return [];
    // Map position tickers to sectors via watchlist data
    const sectorMap = new Map(watchlist.map((w) => [w.ticker, w.sector ?? "Other"]));
    const sectorCounts = new Map<string, number>();
    for (const p of positions) {
      const sector = sectorMap.get(p.ticker) ?? "Other";
      sectorCounts.set(sector, (sectorCounts.get(sector) ?? 0) + 1);
    }
    const total = positions.length || 1;
    return [...sectorCounts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([sector, count], i) => ({
        sector,
        pct: Math.round((count / total) * 100),
        color: DONUT_COLORS[i % DONUT_COLORS.length],
      }));
  }, [positions, watchlist]);

  const handleAddTicker = (ticker: string) => {
    setAddingTickers((prev) => new Set(prev).add(ticker));
    addToWatchlist.mutate(ticker, {
      onSettled: () => {
        setAddingTickers((prev) => {
          const next = new Set(prev);
          next.delete(ticker);
          return next;
        });
      },
    });
  };

  return (
    <PageTransition className="space-y-6">
      <MigrationToast />

      {isEmpty && (
        <WelcomeBanner
          onAddTicker={handleAddTicker}
          addingTickers={addingTickers}
        />
      )}

      {/* 1-2. KPIs + Market Indexes (left) | Allocation donut (right, spans both rows) */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <div className="lg:col-span-4 space-y-4">
          <KPIRow />
          <MarketPulseZone />
        </div>
        <div className="lg:col-span-1">
          <Link href="/sectors" className="block h-full">
            <div className="rounded-lg border border-border bg-card p-5 transition-colors hover:border-primary/30 h-full flex flex-col">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground mb-4">Portfolio Allocation</p>
              <div className="flex-1 flex items-center justify-center">
                {allocations.length > 0 ? (
                  <AllocationDonut allocations={allocations} stockCount={positions.length} />
                ) : (
                  <p className="text-xs text-muted-foreground">Add stocks to see allocation</p>
                )}
              </div>
            </div>
          </Link>
        </div>
      </div>

      {/* 3. What to do — action required + sector performance */}
      <ActionRequiredZone />

      {/* 4. Top Movers — gainers + losers horizontal */}
      <TopMoversZone />

      {/* 5. Data Bulletin — tabular watchlist + portfolio metrics */}
      <BulletinZone />

      {/* 6. News full width */}
      <NewsZone />

      {/* 7. Alerts — collapsible at bottom */}
      <AlertsZone />
    </PageTransition>
  );
}
