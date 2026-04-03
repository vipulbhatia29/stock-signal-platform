"use client";

import { cn } from "@/lib/utils";
import type { PortfolioConvergenceResponse } from "@/types/api";

interface ConvergenceSummaryProps {
  data: PortfolioConvergenceResponse | undefined;
  isLoading: boolean;
}

const LABEL_COLORS = {
  bullish: "bg-gain",
  bearish: "bg-loss",
  mixed: "bg-warning",
} as const;

/** Portfolio-level convergence summary — "X% bullish-aligned". */
export function ConvergenceSummary({
  data,
  isLoading,
}: ConvergenceSummaryProps) {
  if (isLoading) {
    return (
      <div className="rounded-lg border border-border bg-card p-4 animate-pulse">
        <div className="h-4 w-36 rounded bg-border mb-3" />
        <div className="h-3 w-full rounded bg-border mb-2" />
        <div className="h-3 w-48 rounded bg-border" />
      </div>
    );
  }

  if (!data) return null;

  const bullPct = Math.round(data.bullish_pct * 100);
  const bearPct = Math.round(data.bearish_pct * 100);
  const mixPct = Math.round(data.mixed_pct * 100);

  return (
    <div className="relative rounded-lg border border-border bg-card p-4 overflow-hidden">
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-primary to-transparent" />
      <div className="text-[9px] font-semibold uppercase tracking-[0.08em] text-subtle mb-2">
        Portfolio Convergence
      </div>

      {/* Stacked bar */}
      <div
        className="flex h-3 w-full overflow-hidden rounded-full mb-3"
        role="img"
        aria-label={`${bullPct}% bullish, ${bearPct}% bearish, ${mixPct}% mixed`}
      >
        {bullPct > 0 && (
          <div
            className="bg-gain transition-all duration-500"
            style={{ width: `${bullPct}%` }}
          />
        )}
        {mixPct > 0 && (
          <div
            className="bg-warning transition-all duration-500"
            style={{ width: `${mixPct}%` }}
          />
        )}
        {bearPct > 0 && (
          <div
            className="bg-loss transition-all duration-500"
            style={{ width: `${bearPct}%` }}
          />
        )}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 text-xs">
        <LegendItem color="bullish" label="Bullish" pct={bullPct} />
        <LegendItem color="mixed" label="Mixed" pct={mixPct} />
        <LegendItem color="bearish" label="Bearish" pct={bearPct} />
      </div>

      {/* Divergent positions */}
      {data.divergent_positions.length > 0 && (
        <div className="mt-3 text-xs text-warning">
          Divergent: {data.divergent_positions.join(", ")}
        </div>
      )}
    </div>
  );
}

function LegendItem({
  color,
  label,
  pct,
}: {
  color: keyof typeof LABEL_COLORS;
  label: string;
  pct: number;
}) {
  return (
    <div className="flex items-center gap-1">
      <span className={cn("h-2 w-2 rounded-full", LABEL_COLORS[color])} />
      <span className="text-muted-foreground">
        {label} {pct}%
      </span>
    </div>
  );
}
