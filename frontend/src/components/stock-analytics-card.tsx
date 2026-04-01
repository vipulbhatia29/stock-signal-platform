"use client";

import { SectionHeading } from "@/components/section-heading";
import type { StockAnalyticsResponse } from "@/types/api";

interface StockAnalyticsCardProps {
  analytics: StockAnalyticsResponse | undefined;
  isLoading: boolean;
}

function MetricRow({
  label,
  value,
  suffix,
  accent,
}: {
  label: string;
  value: number | null | undefined;
  suffix?: string;
  accent?: "gain" | "loss" | "neutral";
}) {
  const formatted =
    value != null ? `${value.toFixed(2)}${suffix ?? ""}` : "\u2014";
  const color =
    accent === "gain"
      ? "text-gain"
      : accent === "loss"
        ? "text-loss"
        : "text-foreground";
  return (
    <div className="flex items-center justify-between py-1.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={`text-sm font-medium ${color}`}>{formatted}</span>
    </div>
  );
}

export function StockAnalyticsCard({
  analytics,
  isLoading,
}: StockAnalyticsCardProps) {
  if (isLoading) {
    return (
      <div className="rounded-lg border border-border bg-card2 p-4">
        <SectionHeading>Risk Analytics</SectionHeading>
        <div className="h-24 animate-pulse rounded bg-muted" />
      </div>
    );
  }

  const hasData =
    analytics &&
    (analytics.sortino != null ||
      analytics.max_drawdown != null ||
      analytics.alpha != null ||
      analytics.beta != null);

  return (
    <div className="rounded-lg border border-border bg-card2 p-4">
      <SectionHeading>Risk Analytics (vs SPY)</SectionHeading>
      {!hasData ? (
        <p className="text-xs text-muted-foreground">
          Risk analytics not yet available. Data is computed during the nightly
          pipeline and requires at least 30 days of price history.
        </p>
      ) : (
        <div className="divide-y divide-border">
          <MetricRow
            label="Sortino Ratio"
            value={analytics.sortino}
            accent={
              analytics.sortino != null
                ? analytics.sortino >= 1
                  ? "gain"
                  : analytics.sortino < 0
                    ? "loss"
                    : "neutral"
                : "neutral"
            }
          />
          <MetricRow
            label="Max Drawdown"
            value={
              analytics.max_drawdown != null
                ? analytics.max_drawdown * 100
                : null
            }
            suffix="%"
            accent={
              analytics.max_drawdown != null && analytics.max_drawdown > 0.15
                ? "loss"
                : "neutral"
            }
          />
          <MetricRow
            label="Alpha"
            value={analytics.alpha}
            accent={
              analytics.alpha != null
                ? analytics.alpha >= 0
                  ? "gain"
                  : "loss"
                : "neutral"
            }
          />
          <MetricRow
            label="Beta"
            value={analytics.beta}
            accent="neutral"
          />
        </div>
      )}
    </div>
  );
}
