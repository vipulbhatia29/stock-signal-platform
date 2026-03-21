"use client";

import { useTrendingStocks } from "@/hooks/use-stocks";
import { SectionHeading } from "@/components/section-heading";
import { Sparkline } from "@/components/sparkline";
import Link from "next/link";

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
        {items.map((item) => (
          <Link
            key={item.ticker}
            href={`/stocks/${item.ticker}`}
            className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-3 transition-colors hover:border-[var(--color-accent)]/50"
          >
            <div className="min-w-0">
              <p className="text-sm font-semibold text-[var(--color-foreground)] truncate">
                {item.ticker}
              </p>
              <p className="text-xs text-[var(--color-muted-foreground)] truncate">
                {item.name}
              </p>
              <p className="mt-0.5 text-xs font-mono">
                <span
                  className={
                    (item.composite_score ?? 0) >= 7
                      ? "text-[var(--color-gain)]"
                      : (item.composite_score ?? 0) >= 4
                        ? "text-[var(--color-foreground)]"
                        : "text-[var(--color-loss)]"
                  }
                >
                  {item.composite_score?.toFixed(1) ?? "—"}/10
                </span>
              </p>
            </div>
            {item.price_history && item.price_history.length > 1 && (
              <div className="ml-2 w-16 shrink-0">
                <Sparkline
                  data={item.price_history}
                  width={64}
                  height={24}
                />
              </div>
            )}
          </Link>
        ))}
      </div>
    </div>
  );
}
