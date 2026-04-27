"use client";

import { Briefcase } from "lucide-react";
import { SectionHeading } from "@/components/section-heading";
import { PortfolioKPITile } from "@/components/portfolio-kpi-tile";
import { HealthGradeBadge } from "@/components/health-grade-badge";
import { EmptyState } from "@/components/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { usePortfolioSummary, usePortfolioHealth, usePortfolioAnalytics, usePortfolioHealthHistory } from "@/hooks/use-stocks";
import { usePortfolioConvergence } from "@/hooks/use-convergence";
import { usePortfolioForecastFull } from "@/hooks/use-forecasts";
import { LineChart, Line, ResponsiveContainer } from "recharts";
import { cn } from "@/lib/utils";
import { formatCurrency } from "@/lib/format";

/** Portfolio deep-dive — health, analytics, convergence, forecast. KPIs are in KPIRow. */
export function PortfolioZone() {
  const { data: summary, isLoading: summaryLoading } = usePortfolioSummary();
  const { data: health, isLoading: healthLoading } = usePortfolioHealth();
  const { data: analytics } = usePortfolioAnalytics();
  const { data: healthHistory } = usePortfolioHealthHistory(7);
  const portfolioId = summary?.portfolio_id ?? null;
  const { data: convergence } = usePortfolioConvergence(portfolioId, !!summary);
  const { data: forecast } = usePortfolioForecastFull(portfolioId);

  const isLoading = summaryLoading || healthLoading;

  if (isLoading) {
    return (
      <section aria-label="Portfolio Analytics">
        <SectionHeading>Portfolio Analytics</SectionHeading>
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
      <section aria-label="Portfolio Analytics">
        <SectionHeading>Portfolio Analytics</SectionHeading>
        <EmptyState icon={Briefcase} title="No portfolio yet" description="Log your first transaction to see portfolio analytics here" />
      </section>
    );
  }

  return (
    <section aria-label="Portfolio Analytics">
      <SectionHeading>Portfolio Analytics</SectionHeading>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {/* Health Grade */}
        <div className="flex flex-col items-start gap-2">
          <PortfolioKPITile label="Health Grade" value={health?.grade ?? "—"} accent="neutral" />
          {health && <HealthGradeBadge grade={health.grade} score={health.health_score} />}
          {health && healthHistory && healthHistory.length >= 2 && (
            <div className={cn(
              "h-8 w-full mt-1",
              health?.grade && ["A", "B"].includes(health.grade) ? "text-gain" :
              health?.grade === "C" ? "text-amber-400" : "text-loss"
            )}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={healthHistory}>
                  <Line
                    type="monotone"
                    dataKey="health_score"
                    stroke="currentColor"
                    strokeWidth={1.5}
                    dot={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        {/* Cost Basis */}
        <PortfolioKPITile label="Cost Basis" value={formatCurrency(summary.total_cost_basis)} accent="neutral" />

        {/* Convergence */}
        {convergence ? (
          <PortfolioKPITile
            label="Convergence"
            value={`${Math.round(convergence.bullish_pct * 100)}% bullish`}
            subtext={convergence.divergent_positions.length > 0
              ? `${convergence.divergent_positions.length} divergent`
              : undefined}
            accent={convergence.bullish_pct >= 0.5 ? "gain" : convergence.bearish_pct >= 0.5 ? "loss" : "neutral"}
          />
        ) : (
          <PortfolioKPITile label="Convergence" value="—" accent="neutral" />
        )}

        {/* BL Return */}
        {forecast ? (
          <PortfolioKPITile
            label="BL Return"
            value={`${forecast.bl.portfolio_expected_return >= 0 ? "+" : ""}${(forecast.bl.portfolio_expected_return * 100).toFixed(1)}%`}
            subtext="annualized"
            accent={forecast.bl.portfolio_expected_return >= 0 ? "gain" : "loss"}
          />
        ) : (
          <PortfolioKPITile label="BL Return" value="—" accent="neutral" />
        )}
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
    </section>
  );
}
