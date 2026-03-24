"use client";

import { cn } from "@/lib/utils";
import { formatSignalLabel } from "@/lib/signals";

interface StockMetricsProps {
  rsiValue: number | null;
  macdSignal: string | null;
  smaSignal: string | null;
  sharpeRatio: number | null;
  className?: string;
}

function metricColor(signal: string | null): string {
  if (!signal) return "text-muted-foreground";
  const s = signal.toUpperCase();
  if (
    s.includes("BULLISH") ||
    s === "OVERSOLD" ||
    s === "ABOVE_200" ||
    s === "GOLDEN_CROSS"
  )
    return "text-gain";
  if (
    s.includes("BEARISH") ||
    s === "OVERBOUGHT" ||
    s === "BELOW_200" ||
    s === "DEATH_CROSS"
  )
    return "text-loss";
  return "text-muted-foreground";
}

function rsiColor(value: number | null): string {
  if (value == null) return "text-muted-foreground";
  if (value >= 70) return "text-loss"; // overbought
  if (value <= 30) return "text-gain"; // oversold (buying opportunity)
  return "text-muted-foreground";
}

function sharpeColor(value: number | null): string {
  if (value == null) return "text-muted-foreground";
  if (value >= 1) return "text-gain";
  if (value >= 0.5) return "text-foreground";
  return "text-loss";
}

export function StockMetrics({
  rsiValue,
  macdSignal,
  smaSignal,
  sharpeRatio,
  className,
}: StockMetricsProps) {
  return (
    <div className={cn("grid grid-cols-2 gap-x-3 gap-y-0.5", className)}>
      <div className="flex justify-between text-[9px]">
        <span className="text-muted-foreground">RSI</span>
        <span className={cn("font-mono", rsiColor(rsiValue))}>
          {rsiValue?.toFixed(0) ?? "—"}
        </span>
      </div>
      <div className="flex justify-between text-[9px]">
        <span className="text-muted-foreground">MACD</span>
        <span className={cn("font-mono", metricColor(macdSignal))}>
          {formatSignalLabel(macdSignal)}
        </span>
      </div>
      <div className="flex justify-between text-[9px]">
        <span className="text-muted-foreground">SMA</span>
        <span className={cn("font-mono", metricColor(smaSignal))}>
          {formatSignalLabel(smaSignal)}
        </span>
      </div>
      <div className="flex justify-between text-[9px]">
        <span className="text-muted-foreground">Sharpe</span>
        <span className={cn("font-mono", sharpeColor(sharpeRatio))}>
          {sharpeRatio?.toFixed(2) ?? "—"}
        </span>
      </div>
    </div>
  );
}

/**
 * Compact metric guide — explains what the metrics mean.
 * Shows as a subtle footer when the card has space.
 */
export function MetricGuide({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "text-[8px] text-muted-foreground/60 leading-[1.4] border-t border-border/50 pt-1.5 mt-1.5",
        className
      )}
    >
      <span className="text-gain">RSI &lt;30</span> oversold (buy opportunity) ·{" "}
      <span className="text-loss">RSI &gt;70</span> overbought ·{" "}
      <span className="text-gain">Sharpe &gt;1</span> strong risk-adjusted return
    </div>
  );
}
