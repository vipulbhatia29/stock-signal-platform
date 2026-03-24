"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import { XIcon, RefreshCw, CheckCircle2 } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { RelativeTime } from "./relative-time";
import { cn } from "@/lib/utils";

function isStale(
  priceUpdatedAt: string,
  acknowledgedAt: string | null | undefined
): boolean {
  const priceDate = new Date(priceUpdatedAt).getTime();
  const ageMs = Date.now() - priceDate;
  const isOld = ageMs > 60 * 60 * 1000;
  if (!isOld) return false;
  if (!acknowledgedAt) return true;
  return priceDate > new Date(acknowledgedAt).getTime();
}

function scoreToSignal(score: number | null | undefined): "BUY" | "WATCH" | "AVOID" {
  if (score == null) return "WATCH";
  // Matches backend: BUY >= 8, WATCH >= 5, AVOID < 5
  if (score >= 8) return "BUY";
  if (score >= 5) return "WATCH";
  return "AVOID";
}

interface StockCardProps {
  ticker: string;
  name: string | null;
  sector: string | null;
  score?: number | null;
  onRemove: () => void;
  animationDelay?: number;
  currentPrice?: number | null;
  priceUpdatedAt?: string | null;
  onRefresh?: (ticker: string) => void;
  isRefreshing?: boolean;
  priceAcknowledgedAt?: string | null;
  onAcknowledge?: (ticker: string) => void;
}

export function StockCard({
  ticker,
  name,
  sector, // eslint-disable-line @typescript-eslint/no-unused-vars
  score,
  onRemove,
  animationDelay = 0,
  currentPrice,
  priceUpdatedAt,
  onRefresh,
  isRefreshing: isRefreshingProp = false,
  priceAcknowledgedAt,
  onAcknowledge,
}: StockCardProps) {
  const [localRefreshing, setLocalRefreshing] = useState(false);
  const [refreshDone, setRefreshDone] = useState(false);
  const isRefreshing = isRefreshingProp || localRefreshing;

  const handleRefresh = useCallback(async () => {
    if (isRefreshing || !onRefresh) return;
    setLocalRefreshing(true);
    setRefreshDone(false);
    try {
      await onRefresh(ticker);
      setRefreshDone(true);
      setTimeout(() => setRefreshDone(false), 2000);
    } finally {
      setLocalRefreshing(false);
    }
  }, [ticker, onRefresh, isRefreshing]);

  const signal = scoreToSignal(score);
  // composite_score is 0-10 from API, convert to 0-100% for bar width
  const scoreBarPct = score != null ? Math.round(score * 10) : 0;
  const scoreBarColor =
    signal === "BUY"
      ? "var(--gain)"
      : signal === "AVOID"
        ? "var(--loss)"
        : "var(--cyan)";
  const stale =
    priceUpdatedAt ? isStale(priceUpdatedAt, priceAcknowledgedAt) : false;

  const signalClasses =
    signal === "BUY"
      ? "text-[var(--gain)] bg-[var(--gain)]/10"
      : signal === "AVOID"
        ? "text-[var(--loss)] bg-[var(--loss)]/10"
        : "text-[var(--cyan)] bg-[var(--cdim)]";

  return (
    <div
      className="group relative rounded-[var(--radius)] border border-border bg-card p-[12px_13px] flex flex-col gap-2.5 cursor-pointer transition-colors hover:border-[var(--bhi)] hover:bg-[var(--hov)] animate-fade-slide-up max-w-sm"
      style={{ "--stagger-delay": `${animationDelay}ms` } as React.CSSProperties}
    >
      {/* Remove button */}
      <button
        className="absolute top-2 right-2 w-5 h-5 rounded flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-foreground"
        onClick={(e) => {
          e.preventDefault();
          onRemove();
        }}
        aria-label={`Remove ${ticker}`}
      >
        <XIcon size={11} />
      </button>

      <Link href={`/stocks/${ticker}`} className="flex flex-col gap-2.5">
        {/* Top row: ticker + price */}
        <div className="flex items-start justify-between pr-5">
          <div>
            <div className="font-mono text-[14px] font-semibold text-foreground">
              {ticker}
            </div>
            <div className="text-[10px] text-muted-foreground mt-0.5 truncate max-w-[120px]">
              {name || "—"}
            </div>
          </div>
          <div className="text-right">
            {currentPrice != null ? (
              <div className="font-mono text-[14px] font-semibold text-foreground">
                ${currentPrice.toFixed(2)}
              </div>
            ) : (
              <div className="text-[10px] text-muted-foreground">—</div>
            )}
          </div>
        </div>

        {/* Bottom row: signal badge + score + score bar + refresh */}
        <div className="flex items-center justify-between">
          <span
            className={cn(
              "inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold tracking-wide",
              signalClasses
            )}
            title={`Signal: ${signal} — based on composite technical + fundamental analysis`}
          >
            {signal}
          </span>

          <div className="flex items-center gap-2 flex-1 mx-3 min-w-0 overflow-hidden">
            <div className="flex-1 h-[3px] rounded-full bg-[var(--cdim)] min-w-0" title={`Composite score: ${(score != null ? score.toFixed(1) : "N/A")}/10`}>
              <div
                className="h-full rounded-full transition-all"
                style={{ width: `${scoreBarPct}%`, background: scoreBarColor }}
              />
            </div>
            <span className="font-mono text-[9.5px] text-muted-foreground shrink-0" title="Score out of 10">
              {score != null ? score.toFixed(1) : "—"}
            </span>
          </div>

          {/* Refresh controls */}
          <div className="flex items-center gap-0.5">
            {priceUpdatedAt && (
              <span className="text-[9px] text-muted-foreground hidden group-hover:block">
                <RelativeTime date={priceUpdatedAt} />
              </span>
            )}
            <button
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                handleRefresh();
              }}
              disabled={isRefreshing}
              aria-label={`Refresh ${ticker}`}
              className={cn(
                "p-0.5 rounded-full transition-colors",
                isRefreshing && "animate-spin pointer-events-none",
                refreshDone
                  ? "text-gain"
                  : stale
                    ? "text-[var(--warning)]"
                    : "text-muted-foreground hover:text-foreground"
              )}
            >
              {refreshDone ? <CheckCircle2 size={10} /> : <RefreshCw size={10} />}
            </button>
            {stale && onAcknowledge && (
              <button
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onAcknowledge(ticker);
                }}
                aria-label={`Dismiss stale alert for ${ticker}`}
                className="p-0.5 text-[var(--warning)] hover:text-muted-foreground text-[9px] leading-none"
              >
                ✕
              </button>
            )}
          </div>
        </div>
      </Link>
    </div>
  );
}

export function StockCardSkeleton() {
  return (
    <div className="rounded-[var(--radius)] border border-border bg-card p-[12px_13px] flex flex-col gap-2.5">
      <div className="flex items-start justify-between">
        <div>
          <Skeleton className="h-4 w-14 mb-1" />
          <Skeleton className="h-3 w-20" />
        </div>
        <Skeleton className="h-4 w-16" />
      </div>
      <div className="flex items-center gap-2">
        <Skeleton className="h-4 w-10" />
        <Skeleton className="h-[3px] flex-1" />
      </div>
    </div>
  );
}
