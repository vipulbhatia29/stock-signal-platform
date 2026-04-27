"use client";

import { usePortfolioSummary, useWatchlist, usePositions } from "@/hooks/use-stocks";
import { PortfolioKPITile } from "@/components/portfolio-kpi-tile";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCurrency } from "@/lib/format";
import { useMemo } from "react";

/** Top row — Portfolio Value (with daily glow), P&L, Signals summary, Top Signal. */
export function KPIRow() {
  const { data: summary, isLoading: summaryLoading } = usePortfolioSummary();
  const { data: watchlist } = useWatchlist();
  const { data: positions } = usePositions();

  const signalCounts = useMemo(() => {
    if (!watchlist) return { buy: 0, watch: 0, avoid: 0 };
    let buy = 0, watch = 0, avoid = 0;
    for (const w of watchlist) {
      if (w.recommendation === "BUY") buy++;
      else if (w.recommendation === "WATCH") watch++;
      else if (w.recommendation === "AVOID") avoid++;
    }
    return { buy, watch, avoid };
  }, [watchlist]);

  const topSignal = useMemo(() => {
    if (!watchlist) return null;
    return watchlist
      .filter((w) => w.composite_score != null)
      .sort((a, b) => (b.composite_score ?? 0) - (a.composite_score ?? 0))[0] ?? null;
  }, [watchlist]);

  // Today's portfolio change: sum of (shares × price × change_pct/100)
  const dailyChange = useMemo(() => {
    if (!positions?.length || !watchlist?.length) return null;
    const watchMap = new Map(watchlist.map((w) => [w.ticker, w]));
    let totalChange = 0;
    let hasData = false;
    for (const p of positions) {
      const w = watchMap.get(p.ticker);
      if (w?.current_price != null && w?.change_pct != null) {
        totalChange += p.shares * w.current_price * (w.change_pct / 100);
        hasData = true;
      }
    }
    return hasData ? totalChange : null;
  }, [positions, watchlist]);

  if (summaryLoading) {
    return (
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-20 rounded-lg bg-card2" />
        ))}
      </div>
    );
  }

  const pnlAccent = summary && summary.unrealized_pnl >= 0 ? "gain" as const : "loss" as const;
  const pnlPctStr = summary?.unrealized_pnl_pct != null
    ? `${summary.unrealized_pnl_pct >= 0 ? "+" : ""}${summary.unrealized_pnl_pct.toFixed(1)}%`
    : undefined;

  const totalSignals = signalCounts.buy + signalCounts.watch + signalCounts.avoid;

  // Determine glow direction from daily change
  const portfolioGlow = dailyChange != null
    ? (dailyChange >= 0 ? "gain" as const : "loss" as const)
    : undefined;
  const dailyStr = dailyChange != null
    ? `Today: ${dailyChange >= 0 ? "+" : ""}${formatCurrency(dailyChange)}`
    : undefined;

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <PortfolioKPITile
        label="Portfolio Value"
        value={summary ? formatCurrency(summary.total_value) : "—"}
        subtext={dailyStr ?? (summary ? `${summary.position_count} positions` : undefined)}
        accent="neutral"
        glow={portfolioGlow}
      />
      <PortfolioKPITile
        label="Unrealized P&L"
        value={summary ? formatCurrency(summary.unrealized_pnl) : "—"}
        subtext={pnlPctStr}
        accent={summary ? pnlAccent : "neutral"}
      />
      <PortfolioKPITile
        label="Signals"
        value={totalSignals > 0 ? `${signalCounts.buy} Buy` : "—"}
        subtext={totalSignals > 0 ? `${signalCounts.watch} Watch · ${signalCounts.avoid} Avoid` : "Add stocks to get signals"}
        accent={signalCounts.buy > 0 ? "gain" : "neutral"}
      />
      <PortfolioKPITile
        label="Top Signal"
        value={topSignal?.ticker ?? "—"}
        subtext={topSignal ? `Score ${topSignal.composite_score?.toFixed(1)}` : undefined}
        accent="neutral"
      />
    </div>
  );
}
