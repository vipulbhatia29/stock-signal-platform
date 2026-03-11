"use client";

import Link from "next/link";
import { XIcon, RefreshCw } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ScoreBadge } from "@/components/score-badge";
import { RelativeTime } from "./relative-time";
import { cn } from "@/lib/utils";

function isStale(dateStr: string): boolean {
  const ageMs = Date.now() - new Date(dateStr).getTime();
  return ageMs > 60 * 60 * 1000; // > 1 hour
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
}

export function StockCard({
  ticker,
  name,
  sector,
  score,
  onRemove,
  animationDelay = 0,
  currentPrice,
  priceUpdatedAt,
  onRefresh,
  isRefreshing = false,
}: StockCardProps) {
  return (
    <Card
      className="group relative transition-colors hover:border-foreground/20 animate-fade-slide-up"
      style={{ '--stagger-delay': `${animationDelay}ms` } as React.CSSProperties}
    >
      <Button
        variant="ghost"
        size="icon"
        className="absolute top-2 right-2 size-6 opacity-0 group-hover:opacity-100 transition-opacity"
        onClick={(e) => {
          e.preventDefault();
          onRemove();
        }}
        aria-label={`Remove ${ticker}`}
      >
        <XIcon className="size-3.5" />
      </Button>
      <Link href={`/stocks/${ticker}`}>
        <CardHeader className="pb-1">
          <div className="flex items-center justify-between pr-6">
            <span className="font-mono text-base font-semibold">{ticker}</span>
            <ScoreBadge score={score ?? null} size="sm" />
          </div>
          {currentPrice != null && (
            <div className="flex items-center justify-between mt-1">
              <span className="text-lg font-semibold">
                ${currentPrice.toFixed(2)}
              </span>
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                {priceUpdatedAt && (
                  <RelativeTime date={priceUpdatedAt} prefix="Refreshed" />
                )}
                <button
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    onRefresh?.(ticker);
                  }}
                  aria-label={`Refresh ${ticker} price data`}
                  className={cn(
                    "ml-1 rounded-full p-0.5 hover:bg-muted transition-colors",
                    isRefreshing && "animate-spin pointer-events-none",
                    priceUpdatedAt && isStale(priceUpdatedAt)
                      ? "text-amber-500"
                      : "text-muted-foreground"
                  )}
                >
                  <RefreshCw className="h-3 w-3" />
                </button>
              </div>
            </div>
          )}
        </CardHeader>
        <CardContent className="space-y-1">
          <p className="truncate text-sm text-muted-foreground">
            {name || "—"}
          </p>
          {sector && (
            <span className="inline-flex rounded-md border px-1.5 py-0.5 text-xs text-muted-foreground">
              {sector}
            </span>
          )}
        </CardContent>
      </Link>
    </Card>
  );
}

export function StockCardSkeleton() {
  return (
    <Card>
      <CardHeader className="pb-1">
        <div className="flex items-center justify-between">
          <Skeleton className="h-5 w-16" />
          <Skeleton className="h-5 w-10" />
        </div>
      </CardHeader>
      <CardContent className="space-y-1">
        <Skeleton className="h-4 w-28" />
        <Skeleton className="h-5 w-16" />
      </CardContent>
    </Card>
  );
}
