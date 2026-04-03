"use client";

import { cn } from "@/lib/utils";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import type { BLSummary } from "@/types/api";

interface BLForecastCardProps {
  data: BLSummary | undefined;
  isLoading: boolean;
}

/** Black-Litterman expected return card with per-position breakdown. */
export function BLForecastCard({ data, isLoading }: BLForecastCardProps) {
  if (isLoading) {
    return (
      <div className="rounded-lg border border-border bg-card p-4 animate-pulse">
        <div className="h-4 w-32 rounded bg-border mb-3" />
        <div className="h-8 w-20 rounded bg-border mb-2" />
        <div className="space-y-1.5">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-3 w-full rounded bg-border" />
          ))}
        </div>
      </div>
    );
  }

  if (!data) return null;

  const pctReturn = data.portfolio_expected_return * 100;
  const isPositive = pctReturn > 0;
  const ReturnIcon = isPositive ? TrendingUp : pctReturn < 0 ? TrendingDown : Minus;

  return (
    <div className="relative rounded-lg border border-border bg-card p-4 overflow-hidden">
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-primary to-transparent" />
      <div className="text-[9px] font-semibold uppercase tracking-[0.08em] text-subtle mb-1">
        BL Expected Return (annualized)
      </div>
      <div className="flex items-center gap-2 mb-3">
        <ReturnIcon
          className={cn(
            "h-5 w-5",
            isPositive ? "text-gain" : pctReturn < 0 ? "text-loss" : "text-subtle",
          )}
          aria-hidden="true"
        />
        <span
          className={cn(
            "font-mono text-2xl font-bold",
            isPositive ? "text-gain" : pctReturn < 0 ? "text-loss" : "text-foreground",
          )}
        >
          {isPositive ? "+" : ""}
          {pctReturn.toFixed(1)}%
        </span>
      </div>

      {data.per_ticker.length > 0 && (
        <div className="space-y-1">
          <div className="text-[9px] font-semibold uppercase tracking-[0.08em] text-subtle">
            Per-position breakdown
          </div>
          {data.per_ticker.map((t) => {
            const ret = t.expected_return * 100;
            return (
              <div
                key={t.ticker}
                className="flex items-center justify-between text-xs"
              >
                <span className="text-muted-foreground">{t.ticker}</span>
                <span
                  className={cn(
                    "font-mono",
                    ret > 0 ? "text-gain" : ret < 0 ? "text-loss" : "text-foreground",
                  )}
                >
                  {ret > 0 ? "+" : ""}
                  {ret.toFixed(1)}%
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
