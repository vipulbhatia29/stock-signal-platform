"use client";

import Link from "next/link";
import { XIcon, RefreshCw } from "lucide-react";
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

function scoreToSignal(score: number | null | undefined): "BUY" | "HOLD" | "SELL" {
  if (score == null) return "HOLD";
  if (score >= 0.6) return "BUY";
  if (score >= 0.4) return "HOLD";
  return "SELL";
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
  isRefreshing = false,
  priceAcknowledgedAt,
  onAcknowledge,
}: StockCardProps) {
  const signal = scoreToSignal(score);
  const scoreBarPct = score != null ? Math.round(score * 100) : 0;
  const scoreBarColor =
    signal === "BUY"
      ? "var(--gain)"
      : signal === "SELL"
        ? "var(--loss)"
        : "var(--cyan)";
  const stale =
    priceUpdatedAt ? isStale(priceUpdatedAt, priceAcknowledgedAt) : false;

  const signalClasses =
    signal === "BUY"
      ? "text-[var(--gain)] bg-[var(--gain)]/10"
      : signal === "SELL"
        ? "text-[var(--loss)] bg-[var(--loss)]/10"
        : "text-[var(--cyan)] bg-[var(--cdim)]";

  return (
    <div
      className="group relative rounded-[var(--radius)] border border-border bg-card p-[12px_13px] flex flex-col gap-2.5 cursor-pointer transition-colors hover:border-[var(--bhi)] hover:bg-[var(--hov)] animate-fade-slide-up"
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

        {/* Bottom row: signal badge + score bar + refresh */}
        <div className="flex items-center justify-between">
          <span
            className={cn(
              "inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold tracking-wide",
              signalClasses
            )}
          >
            {signal}
          </span>

          <div className="flex items-center gap-2 flex-1 mx-3">
            <div className="flex-1 h-[3px] rounded-full bg-[var(--cdim)]">
              <div
                className="h-full rounded-full transition-all"
                style={{ width: `${scoreBarPct}%`, background: scoreBarColor }}
              />
            </div>
            <span className="font-mono text-[9.5px] text-muted-foreground">
              {scoreBarPct}
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
                onRefresh?.(ticker);
              }}
              aria-label={`Refresh ${ticker}`}
              className={cn(
                "p-0.5 rounded-full transition-colors",
                isRefreshing && "animate-spin pointer-events-none",
                stale
                  ? "text-[var(--warning)]"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              <RefreshCw size={10} />
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
