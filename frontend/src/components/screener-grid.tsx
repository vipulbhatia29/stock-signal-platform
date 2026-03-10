"use client";

import { useRef } from "react";
import { useRouter } from "next/navigation";
import { Skeleton } from "@/components/ui/skeleton";
import { ScoreBadge } from "@/components/score-badge";
import { SignalBadge } from "@/components/signal-badge";
import { Sparkline } from "@/components/sparkline";
import { formatPercent } from "@/lib/format";
import { scoreToSentiment } from "@/lib/signals";
import { useContainerWidth } from "@/hooks/use-container-width";
import { cn } from "@/lib/utils";
import type { BulkSignalItem } from "@/types/api";

// ── Stock card ────────────────────────────────────────────────────────────────

function StockCard({ item }: { item: BulkSignalItem }) {
  const router = useRouter();
  const chartRef = useRef<HTMLDivElement | null>(null);
  const chartWidth = useContainerWidth(chartRef);
  const sentiment = scoreToSentiment(item.composite_score);

  return (
    <div
      className="group rounded-lg border bg-card overflow-hidden cursor-pointer hover:border-primary/50 transition-colors"
      onClick={() => router.push(`/stocks/${item.ticker}`)}
      role="button"
      tabIndex={0}
      aria-label={`View ${item.ticker} — ${item.name}`}
      onKeyDown={(e) => e.key === "Enter" && router.push(`/stocks/${item.ticker}`)}
    >
      {/* Sparkline — full-width top half */}
      <div ref={chartRef} className="w-full border-b border-border/50">
        {item.price_history && item.price_history.length >= 2 ? (
          <Sparkline
            data={item.price_history}
            width={chartWidth}
            height={56}
            sentiment={sentiment}
          />
        ) : (
          <div className="h-14 bg-muted/30" />
        )}
      </div>

      {/* Meta row */}
      <div className="px-3 py-2 flex items-center justify-between gap-2">
        {/* Left: ticker + name + signal badges */}
        <div className="min-w-0">
          <div className="flex items-baseline gap-1.5">
            <span className="font-mono font-semibold text-sm tracking-wide">
              {item.ticker}
            </span>
            <span className="text-[10px] text-muted-foreground truncate max-w-[100px]">
              {item.name}
            </span>
          </div>
          <div className="flex gap-1 mt-1 flex-wrap">
            {item.rsi_signal && (
              <SignalBadge signal={item.rsi_signal} type="rsi" />
            )}
            {item.macd_signal && (
              <SignalBadge signal={item.macd_signal} type="macd" />
            )}
            {item.sma_signal && (
              <SignalBadge signal={item.sma_signal} type="sma" />
            )}
          </div>
        </div>

        {/* Right: annual return + score */}
        <div className="text-right flex-shrink-0">
          {item.annual_return !== null && (
            <div
              className={cn(
                "text-[10px] font-medium tabular-nums",
                item.annual_return >= 0 ? "text-gain" : "text-loss"
              )}
            >
              {item.annual_return >= 0 ? "+" : ""}
              {formatPercent(item.annual_return)}
            </div>
          )}
          <div className="mt-0.5">
            <ScoreBadge score={item.composite_score} size="sm" />
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Loading skeleton ──────────────────────────────────────────────────────────

function StockCardSkeleton() {
  return (
    <div className="rounded-lg border bg-card overflow-hidden">
      <Skeleton className="h-14 w-full rounded-none" />
      <div className="px-3 py-2 space-y-2">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-3 w-16" />
      </div>
    </div>
  );
}

// ── Grid ──────────────────────────────────────────────────────────────────────

interface ScreenerGridProps {
  items: BulkSignalItem[];
  isLoading: boolean;
}

export function ScreenerGrid({ items, isLoading }: ScreenerGridProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
        {Array.from({ length: 10 }).map((_, i) => (
          <StockCardSkeleton key={i} />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
      {items.map((item) => (
        <StockCard key={item.ticker} item={item} />
      ))}
    </div>
  );
}
