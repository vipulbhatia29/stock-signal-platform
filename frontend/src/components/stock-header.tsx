"use client";

import { useRouter } from "next/navigation";
import { X, Bookmark, BookmarkCheck } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { ScoreBadge } from "@/components/score-badge";
import { ChangeIndicator } from "@/components/change-indicator";
import { StalenessBadge } from "@/components/staleness-badge";
import { formatCurrency } from "@/lib/format";

function formatMarketCap(value: number): string {
  if (value >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
  if (value >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
  if (value >= 1e6) return `$${(value / 1e6).toFixed(1)}M`;
  return `$${value.toLocaleString()}`;
}

interface StockHeaderProps {
  ticker: string;
  name: string | null;
  sector: string | null;
  score: number | null;
  currentPrice?: number | null;
  priceChange?: number | null;
  priceChangePct?: number | null;
  marketCap?: number | null;
  isInWatchlist: boolean;
  onToggleWatchlist: () => void;
  isRefreshing?: boolean;
  computedAt?: string | null;
}

export function StockHeader({
  ticker,
  name,
  sector,
  score,
  currentPrice,
  priceChange,
  priceChangePct,
  marketCap,
  isInWatchlist,
  onToggleWatchlist,
  isRefreshing,
  computedAt,
}: StockHeaderProps) {
  const router = useRouter();

  return (
    <div className="space-y-3">
      {/* Close button */}
      <Button
        variant="outline"
        size="sm"
        onClick={() => router.back()}
        className="gap-1.5 text-muted-foreground"
      >
        <X size={14} />
        Close
      </Button>

      {/* Breadcrumb */}
      <div className="flex items-center gap-1.5 text-xs">
        <Link href="/dashboard" className="text-muted-foreground hover:text-foreground">
          Dashboard
        </Link>
        <span className="text-subtle">&gt;</span>
        <span className="font-medium text-foreground">{ticker}</span>
      </div>

      {/* Ticker + Score + Name */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="font-mono text-2xl font-bold">{ticker}</h1>
            <ScoreBadge score={score} size="lg" />
            <span className="text-muted-foreground">{name || "—"}</span>
            {sector && (
              <span className="inline-flex rounded-md border px-2 py-0.5 text-xs text-muted-foreground">
                {sector}
              </span>
            )}
            <StalenessBadge
              lastUpdated={computedAt ?? null}
              slaHours={4}
              refreshing={isRefreshing}
            />
          </div>

          {/* Price + Change */}
          {currentPrice != null && (
            <div className="mt-2 flex items-baseline gap-2">
              <span className="font-mono text-3xl font-bold tracking-tight">
                {formatCurrency(currentPrice)}
              </span>
              {priceChangePct != null && (
                <ChangeIndicator value={priceChangePct} size="sm" showIcon={false} />
              )}
              {priceChange != null && (
                <span className="text-sm text-muted-foreground font-mono">
                  ({priceChange >= 0 ? "+" : ""}{formatCurrency(priceChange)})
                </span>
              )}
            </div>
          )}
          {marketCap != null && (
            <div className="mt-1 text-xs text-muted-foreground">
              Market Cap: {formatMarketCap(marketCap)}
            </div>
          )}
        </div>

        {/* Watchlist toggle */}
        <Button
          variant={isInWatchlist ? "default" : "outline"}
          size="sm"
          onClick={onToggleWatchlist}
          className="gap-1.5"
        >
          {isInWatchlist ? (
            <BookmarkCheck className="size-4" />
          ) : (
            <Bookmark className="size-4" />
          )}
          {isInWatchlist ? "In Watchlist" : "Add to Watchlist"}
        </Button>
      </div>
    </div>
  );
}
