"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import type { ForecastHorizon, ModelAccuracy } from "@/types/api";
import { AccuracyBadge } from "@/components/convergence/accuracy-badge";
import { DrillDownSheet } from "@/components/command-center/drill-down-sheet";

const DIRECTION_CONFIG = {
  bullish: { icon: TrendingUp, label: "Bullish", colorClass: "text-gain" },
  bearish: { icon: TrendingDown, label: "Bearish", colorClass: "text-loss" },
  neutral: { icon: Minus, label: "Neutral", colorClass: "text-subtle" },
} as const;

const CONFIDENCE_COLORS = {
  high: "bg-gain/15 text-gain border-gain/25",
  medium: "bg-warning/15 text-warning border-warning/25",
  low: "bg-loss/15 text-loss border-loss/25",
} as const;

const DRIVER_TOOLTIPS: Record<string, string> = {
  "Recent price trend": "Short-term price momentum over the last 21 trading days",
  "3-month momentum": "Medium-term price trend over the last 63 trading days",
  "6-month momentum": "Longer-term price trend over the last 126 trading days",
  "Overbought/oversold level": "RSI indicates whether the stock may be overbought (>70) or oversold (<30)",
  "Trend strength": "MACD histogram measures the strength and direction of the current price trend",
  "Moving average signal": "Whether price is above or below key moving averages (50-day, 200-day)",
  "Price vs. trading range": "Where the price sits relative to its Bollinger Bands (upper, middle, lower)",
  "Price volatility": "How much the stock price fluctuates — higher volatility means more uncertainty",
  "Risk-adjusted returns": "Returns relative to risk taken — higher is better",
  "News sentiment": "Whether recent news coverage for this stock is positive, negative, or neutral",
  "Sector outlook": "Overall sentiment for this stock's industry sector",
  "Economic outlook": "Broader economic sentiment from macro indicators",
  "Signal agreement": "How many technical signals agree on direction (0-6)",
  "Overall signal score": "Composite score across all technical indicators",
  "Market fear index": "VIX level — higher values indicate more market uncertainty",
  "Market trend": "Overall market direction based on S&P 500 momentum",
};

interface ForecastCardProps {
  horizons: ForecastHorizon[] | undefined;
  isLoading: boolean;
  currentPrice?: number;
  modelAccuracy?: ModelAccuracy | null;
  modelStatus?: string;
}

function DriverChip({ label, direction }: { label: string; direction: string }) {
  const isBullish = direction === "bullish";
  const arrow = isBullish ? "↑" : "↓";
  const tooltip = DRIVER_TOOLTIPS[label];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[9px] font-medium",
        isBullish ? "bg-gain/10 text-gain" : "bg-loss/10 text-loss",
      )}
      title={tooltip}
    >
      {label} {arrow}
    </span>
  );
}

function HorizonPill({ horizon, currentPrice }: { horizon: ForecastHorizon; currentPrice?: number }) {
  const ret = horizon.expected_return_pct;
  const isPositive = ret > 0;
  const isNegative = ret < 0;
  const dirConfig =
    DIRECTION_CONFIG[horizon.direction as keyof typeof DIRECTION_CONFIG] ??
    DIRECTION_CONFIG.neutral;
  const DirIcon = dirConfig.icon;
  const topDrivers = horizon.drivers?.slice(0, 2) ?? [];

  return (
    <div className="rounded-lg border border-border bg-card/50 p-3">
      {/* Header: horizon + confidence */}
      <div className="flex items-center justify-between mb-1.5">
        <div className="text-[9px] font-semibold uppercase tracking-[0.08em] text-subtle">
          {horizon.horizon_days}D
        </div>
        <div className="flex items-center gap-1">
          <DirIcon className={cn("h-3 w-3", dirConfig.colorClass)} />
          <span className={cn("text-[9px] font-medium", dirConfig.colorClass)}>
            {dirConfig.label}
          </span>
          <span className="text-[9px] text-subtle ml-1">
            {Math.round(horizon.confidence * 100)}%
          </span>
        </div>
      </div>

      {/* Expected return — primary display */}
      <div
        className={cn(
          "font-mono text-lg font-bold leading-none",
          isPositive && "text-gain",
          isNegative && "text-loss",
          !isPositive && !isNegative && "text-subtle",
        )}
      >
        {isPositive ? "+" : ""}
        {ret.toFixed(1)}%
      </div>

      {/* Implied target price — secondary (backend-provided or fallback from currentPrice) */}
      {(() => {
        const target = horizon.implied_target_price ?? (currentPrice ? currentPrice * (1 + ret / 100) : null);
        return target != null ? (
          <div className="mt-0.5 text-[10px] text-subtle font-mono">
            ~${target.toFixed(2)}
          </div>
        ) : null;
      })()}

      {/* Return range */}
      <div className="mt-1.5 text-[9px] text-subtle">
        {horizon.return_lower_pct > 0 ? "+" : ""}
        {horizon.return_lower_pct.toFixed(1)}% to{" "}
        {horizon.return_upper_pct > 0 ? "+" : ""}
        {horizon.return_upper_pct.toFixed(1)}%
      </div>

      {/* Driver chips */}
      {topDrivers.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {topDrivers.map((d) => (
            <DriverChip key={d.feature} label={d.label} direction={d.direction} />
          ))}
        </div>
      )}
    </div>
  );
}

export function ForecastCard({
  horizons,
  isLoading,
  currentPrice,
  modelAccuracy,
  modelStatus,
}: ForecastCardProps) {
  const [drillOpen, setDrillOpen] = useState(false);

  if (isLoading) {
    return (
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="h-4 w-32 rounded bg-muted animate-pulse mb-3" />
        <div className="grid grid-cols-2 gap-3">
          {[0, 1].map((i) => (
            <div
              key={i}
              className="rounded-lg border border-border bg-card/50 p-3 h-28 animate-pulse"
            />
          ))}
        </div>
      </div>
    );
  }

  // Model status states
  if (modelStatus === "pending" || modelStatus === "training") {
    return (
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-subtle mb-2">
          Return Forecast
        </div>
        <div className="text-sm text-subtle">
          {modelStatus === "training"
            ? "Forecast model is training — results available after next nightly run."
            : "Forecast building — requires 2+ weeks of signal data."}
        </div>
      </div>
    );
  }

  if (!horizons || horizons.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-subtle mb-2">
          Return Forecast
        </div>
        <div className="text-sm text-subtle">
          No forecast available. Data is computed nightly.
        </div>
      </div>
    );
  }

  const firstHorizon = horizons[0];
  const confidence = firstHorizon.confidence_level as keyof typeof CONFIDENCE_COLORS;
  const confidenceColor = CONFIDENCE_COLORS[confidence] ?? CONFIDENCE_COLORS.medium;

  return (
    <div className="relative overflow-hidden rounded-lg border border-border bg-card p-4">
      {/* Accent line */}
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-primary to-transparent" />

      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-subtle">
          Return Forecast
        </div>
        <div className="flex items-center gap-2">
          {modelAccuracy != null && (
            <AccuracyBadge accuracy={modelAccuracy} onClick={() => setDrillOpen(true)} />
          )}
          <span
            className={cn(
              "inline-flex items-center rounded border px-1.5 py-0.5 text-[9px] font-semibold uppercase",
              confidenceColor,
            )}
          >
            {confidence} conf
          </span>
          {modelStatus === "degraded" && (
            <span
              className="inline-flex items-center rounded border px-1.5 py-0.5 text-[9px] font-semibold uppercase bg-warning/15 text-warning border-warning/25"
              title="Model accuracy has declined — predictions may be less reliable"
            >
              Degraded
            </span>
          )}
        </div>
      </div>

      {/* Forecast signal — actionability context */}
      {firstHorizon.forecast_signal && (
        <div className="mb-3 text-[10px] text-subtle italic">
          {firstHorizon.forecast_signal === "supports_buy" && "Supports BUY thesis"}
          {firstHorizon.forecast_signal === "supports_caution" && "Supports caution"}
          {firstHorizon.forecast_signal === "insufficient_conviction" && "Insufficient conviction"}
        </div>
      )}

      {/* Horizon pills — 2 columns */}
      <div className="grid grid-cols-2 gap-3">
        {horizons.map((h) => (
          <HorizonPill key={h.horizon_days} horizon={h} currentPrice={currentPrice} />
        ))}
      </div>

      {/* Backtest detail drill-down */}
      {modelAccuracy != null && (
        <DrillDownSheet
          open={drillOpen}
          onClose={() => setDrillOpen(false)}
          title="Forecast Model Detail"
        >
          <div className="space-y-4 text-sm text-foreground">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <span className="text-subtle">Direction Accuracy</span>
              <span className="font-mono font-semibold">
                {Math.round(modelAccuracy.direction_hit_rate * 100)}%
              </span>
            </div>
            <div className="flex items-center justify-between border-b border-border pb-3">
              <span className="text-subtle">Avg Return Error</span>
              <span className="font-mono font-semibold">
                {modelAccuracy.avg_error_pct.toFixed(1)}%
              </span>
            </div>
            <div className="flex items-center justify-between border-b border-border pb-3">
              <span className="text-subtle">CI Containment</span>
              <span className="font-mono font-semibold">
                {Math.round(modelAccuracy.ci_containment_rate * 100)}%
              </span>
            </div>
            <div className="flex items-center justify-between border-b border-border pb-3">
              <span className="text-subtle">Evaluated Forecasts</span>
              <span className="font-mono font-semibold">
                {modelAccuracy.evaluated_count}
              </span>
            </div>
            <p className="text-subtle text-[13px] leading-relaxed">
              Direction accuracy shows how often the model correctly predicted
              whether the stock would go up or down. CI containment measures how
              often the actual return fell within the predicted range.
            </p>
          </div>
        </DrillDownSheet>
      )}
    </div>
  );
}
