"use client";

import { cn } from "@/lib/utils";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import type { ForecastHorizon } from "@/types/api";

const CONFIDENCE_COLORS = {
  high: "bg-gain/15 text-gain border-gain/25",
  medium: "bg-warning/15 text-warning border-warning/25",
  low: "bg-loss/15 text-loss border-loss/25",
} as const;

const SHARPE_ICONS = {
  improving: TrendingUp,
  declining: TrendingDown,
  flat: Minus,
} as const;

interface ForecastCardProps {
  horizons: ForecastHorizon[] | undefined;
  isLoading: boolean;
  currentPrice?: number;
}

function HorizonPill({
  horizon,
  currentPrice,
}: {
  horizon: ForecastHorizon;
  currentPrice?: number;
}) {
  const changePct =
    currentPrice && currentPrice > 0
      ? ((horizon.predicted_price - currentPrice) / currentPrice) * 100
      : null;

  const isPositive = changePct !== null && changePct > 0;
  const isNegative = changePct !== null && changePct < 0;

  return (
    <div className="rounded-lg border border-border bg-card/50 p-3">
      <div className="text-[9px] font-semibold uppercase tracking-[0.08em] text-subtle mb-1.5">
        {horizon.horizon_days}d
      </div>
      <div className="font-mono text-lg font-bold text-foreground leading-none">
        ${horizon.predicted_price.toFixed(0)}
      </div>
      {changePct !== null && (
        <div
          className={cn(
            "mt-1 text-xs font-mono font-medium",
            isPositive && "text-gain",
            isNegative && "text-loss",
            !isPositive && !isNegative && "text-subtle"
          )}
        >
          {isPositive ? "+" : ""}
          {changePct.toFixed(1)}%
        </div>
      )}
      <div className="mt-1.5 text-[9px] text-subtle">
        ${horizon.predicted_lower.toFixed(0)} – $
        {horizon.predicted_upper.toFixed(0)}
      </div>
    </div>
  );
}

export function ForecastCard({
  horizons,
  isLoading,
  currentPrice,
}: ForecastCardProps) {
  if (isLoading) {
    return (
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="h-4 w-32 rounded bg-muted animate-pulse mb-3" />
        <div className="grid grid-cols-3 gap-3">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="rounded-lg border border-border bg-card/50 p-3 h-24 animate-pulse"
            />
          ))}
        </div>
      </div>
    );
  }

  if (!horizons || horizons.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-subtle mb-2">
          Price Forecast
        </div>
        <div className="text-sm text-subtle">
          No forecast available. Data is computed nightly.
        </div>
      </div>
    );
  }

  const firstHorizon = horizons[0];
  const confidence = firstHorizon.confidence_level as keyof typeof CONFIDENCE_COLORS;
  const sharpeKey = firstHorizon.sharpe_direction as keyof typeof SHARPE_ICONS;
  const SharpeIcon = SHARPE_ICONS[sharpeKey] ?? Minus;
  const confidenceColor = CONFIDENCE_COLORS[confidence] ?? CONFIDENCE_COLORS.medium;

  return (
    <div className="relative overflow-hidden rounded-lg border border-border bg-card p-4">
      {/* Accent line */}
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-primary to-transparent" />

      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-subtle">
          Price Forecast
        </div>
        <div className="flex items-center gap-2">
          {/* Confidence badge */}
          <span
            className={cn(
              "inline-flex items-center rounded border px-1.5 py-0.5 text-[9px] font-semibold uppercase",
              confidenceColor
            )}
          >
            {confidence}
          </span>
          {/* Sharpe direction */}
          <span className="inline-flex items-center gap-0.5 text-[9px] text-subtle">
            <SharpeIcon className="h-3 w-3" />
            Sharpe {sharpeKey}
          </span>
        </div>
      </div>

      {/* Horizon pills */}
      <div className="grid grid-cols-3 gap-3">
        {horizons.map((h) => (
          <HorizonPill
            key={h.horizon_days}
            horizon={h}
            currentPrice={currentPrice}
          />
        ))}
      </div>
    </div>
  );
}
