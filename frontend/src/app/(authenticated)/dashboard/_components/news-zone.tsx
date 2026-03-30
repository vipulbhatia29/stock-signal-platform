"use client";

import { Newspaper, ExternalLink } from "lucide-react";
import { SectionHeading } from "@/components/section-heading";
import { EmptyState } from "@/components/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useWatchlist } from "@/hooks/use-stocks";
import { cn } from "@/lib/utils";

/** Zone 5 — Personalized news feed derived from watchlist tickers. */
export function NewsZone() {
  const { data: watchlist, isLoading } = useWatchlist();

  // Currently no dedicated news endpoint exists — show a watchlist-based
  // summary with links out to detail pages where news tools can be invoked.
  const tickers = watchlist?.slice(0, 8) ?? [];

  return (
    <section>
      <SectionHeading>
        <span className="inline-flex items-center gap-1.5">
          <Newspaper className="h-3 w-3" />
          News &amp; Intelligence
        </span>
      </SectionHeading>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full rounded-lg bg-card2" />
          ))}
        </div>
      ) : !tickers.length ? (
        <EmptyState
          icon={Newspaper}
          title="No news yet"
          description="Add stocks to your watchlist to see personalized news"
        />
      ) : (
        <div className="space-y-2">
          {tickers.map((item) => (
            <a
              key={item.ticker}
              href={`/stocks/${item.ticker}`}
              className={cn(
                "flex items-center justify-between rounded-lg border border-border bg-card px-3 py-2.5",
                "transition-colors hover:border-[var(--bhi)] hover:bg-hov"
              )}
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-bold">
                    {item.ticker}
                  </span>
                  <span className="truncate text-[10px] text-muted-foreground">
                    {item.name ?? ""}
                  </span>
                </div>
                <p className="mt-0.5 text-[10px] text-muted-foreground">
                  View latest intelligence, news &amp; analysis
                </p>
              </div>
              <ExternalLink className="ml-2 h-3.5 w-3.5 shrink-0 text-subtle" />
            </a>
          ))}
        </div>
      )}
    </section>
  );
}
