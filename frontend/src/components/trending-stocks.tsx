"use client";

import { useTrendingStocks } from "@/hooks/use-stocks";
import { SectionHeading } from "@/components/section-heading";
import { StockMetrics, MetricGuide } from "@/components/stock-metrics";
import Link from "next/link";
import { cn } from "@/lib/utils";
import type { BulkSignalItem } from "@/types/api";

function scoreToSignal(score: number | null): { label: string; cls: string } {
  if (score == null) return { label: "N/A", cls: "text-muted-foreground bg-muted/20" };
  if (score >= 8) return { label: "BUY", cls: "text-gain bg-gain/10" };
  if (score >= 5) return { label: "WATCH", cls: "text-warning bg-warning/10" };
  return { label: "AVOID", cls: "text-loss bg-loss/10" };
}

export function TrendingStocks() {
  const { data, isLoading } = useTrendingStocks(5);

  if (isLoading) {
    return (
      <div className="mb-8">
        <SectionHeading>Trending</SectionHeading>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <div
              key={i}
              className="h-20 animate-pulse rounded-lg bg-[var(--color-surface-raised)]"
            />
          ))}
        </div>
      </div>
    );
  }

  const items = data?.items ?? [];
  if (items.length === 0) return null;

  return (
    <div className="mb-8">
      <SectionHeading>Trending Stocks</SectionHeading>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {items.map((item: BulkSignalItem) => {
          const signal = scoreToSignal(item.composite_score);
          return (
            <Link
              key={item.ticker}
              href={`/stocks/${item.ticker}`}
              className="group flex flex-col rounded-lg border border-border bg-card p-3 transition-colors hover:border-[var(--bhi)] hover:bg-hov"
            >
              {/* Header: ticker + name */}
              <div className="min-w-0">
                <p className="font-mono text-sm font-semibold text-foreground truncate">
                  {item.ticker}
                </p>
                <p className="text-[10px] text-muted-foreground truncate">
                  {item.name}
                </p>
              </div>

              {/* Signal badge + score */}
              <div className="flex items-center gap-1.5 mt-1.5 mb-2">
                <span className={cn("inline-flex items-center rounded px-1 py-0.5 text-[9px] font-semibold", signal.cls)}>
                  {signal.label}
                </span>
                <span className="font-mono text-[11px] text-muted-foreground">
                  {item.composite_score?.toFixed(1) ?? "—"}/10
                </span>
              </div>

              {/* Always-visible metrics */}
              <StockMetrics
                rsiValue={item.rsi_value}
                macdSignal={item.macd_signal}
                smaSignal={item.sma_signal}
                sharpeRatio={item.sharpe_ratio}
              />

              {/* Metric guide — visible on hover */}
              <div className="opacity-0 max-h-0 group-hover:opacity-100 group-hover:max-h-12 transition-all duration-200 overflow-hidden">
                <MetricGuide />
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
