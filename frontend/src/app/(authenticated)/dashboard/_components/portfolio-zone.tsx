"use client";

import { Briefcase } from "lucide-react";
import { SectionHeading } from "@/components/section-heading";
import { PortfolioKPITile } from "@/components/portfolio-kpi-tile";
import { HealthGradeBadge } from "@/components/health-grade-badge";
import { SectorPerformanceBars } from "@/components/sector-performance-bars";
import { EmptyState } from "@/components/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { usePortfolioSummary, usePortfolioHealth, useMarketBriefing, usePortfolioAnalytics } from "@/hooks/use-stocks";
import { formatCurrency } from "@/lib/format";

/** Zone 3 — Portfolio KPIs + health grade + sector performance. */
export function PortfolioZone() {
  const { data: summary, isLoading: summaryLoading } = usePortfolioSummary();
  const { data: health, isLoading: healthLoading } = usePortfolioHealth();
  const { data: briefing } = useMarketBriefing();
  const { data: analytics } = usePortfolioAnalytics();

  const isLoading = summaryLoading || healthLoading;

  if (isLoading) {
    return (
      <section aria-label="Portfolio Overview">
        <SectionHeading>Portfolio Overview</SectionHeading>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20 rounded-lg bg-card2" />
          ))}
        </div>
      </section>
    );
  }

  if (!summary || summary.position_count === 0) {
    return (
      <section aria-label="Portfolio Overview">
        <SectionHeading>Portfolio Overview</SectionHeading>
        <EmptyState icon={Briefcase} title="No portfolio yet" description="Log your first transaction to see portfolio analytics here" />
      </section>
    );
  }

  const pnlAccent = summary.unrealized_pnl >= 0 ? "gain" as const : "loss" as const;
  const pnlPctStr = summary.unrealized_pnl_pct != null ? `${summary.unrealized_pnl_pct >= 0 ? "+" : ""}${summary.unrealized_pnl_pct.toFixed(1)}%` : undefined;

  const sectorBars = briefing?.sector_performance.map((s) => ({
    sector: s.sector,
    changePct: s.change_pct,
  })) ?? [];

  return (
    <section aria-label="Portfolio Overview">
      <SectionHeading>Portfolio Overview</SectionHeading>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {/* Health Grade */}
        <div className="flex flex-col items-start gap-2">
          <PortfolioKPITile label="Health Grade" value={health?.grade ?? "—"} accent="neutral" />
          {health && <HealthGradeBadge grade={health.grade} score={health.health_score} />}
        </div>

        {/* Unrealized P&L */}
        <PortfolioKPITile label="Unrealized P&L" value={formatCurrency(summary.unrealized_pnl)} subtext={pnlPctStr} accent={pnlAccent} />

        {/* Total Value */}
        <PortfolioKPITile label="Total Value" value={formatCurrency(summary.total_value)} subtext={`${summary.position_count} positions`} accent="neutral" />

        {/* Cost Basis */}
        <PortfolioKPITile label="Cost Basis" value={formatCurrency(summary.total_cost_basis)} accent="neutral" />
      </div>

      {/* QuantStats Analytics Row */}
      {analytics && analytics.data_days != null && analytics.data_days >= 30 && (
        <div className="mt-3 grid grid-cols-3 gap-3">
          <PortfolioKPITile
            label="Sortino"
            value={analytics.sortino?.toFixed(2) ?? "—"}
            accent="neutral"
          />
          <PortfolioKPITile
            label="Max Drawdown"
            value={analytics.max_drawdown != null ? `${(analytics.max_drawdown * 100).toFixed(1)}%` : "—"}
            accent={analytics.max_drawdown != null && analytics.max_drawdown > 0.15 ? "loss" : "neutral"}
          />
          <PortfolioKPITile
            label="Alpha"
            value={analytics.alpha?.toFixed(2) ?? "—"}
            accent={analytics.alpha != null ? (analytics.alpha >= 0 ? "gain" : "loss") : "neutral"}
          />
        </div>
      )}

      {sectorBars.length > 0 && (
        <div className="mt-3">
          <div className="mb-2 text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">Sector Performance</div>
          <SectorPerformanceBars sectors={sectorBars} />
        </div>
      )}
    </section>
  );
}
