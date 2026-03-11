"use client";

import { useMemo, useState } from "react";
import { StarIcon } from "lucide-react";
import {
  useIndexes,
  useWatchlist,
  useAddToWatchlist,
  useRemoveFromWatchlist,
  useIngestTicker,
} from "@/hooks/use-stocks";
import { TickerSearch } from "@/components/ticker-search";
import { IndexCard, IndexCardSkeleton } from "@/components/index-card";
import { StockCard, StockCardSkeleton } from "@/components/stock-card";
import { SectorFilter } from "@/components/sector-filter";
import { EmptyState } from "@/components/empty-state";
import { SectionHeading } from "@/components/section-heading";
import { toast } from "sonner";

export default function DashboardPage() {
  const [sectorFilter, setSectorFilter] = useState<string | null>(null);

  const { data: indexes, isLoading: indexesLoading } = useIndexes();
  const { data: watchlist, isLoading: watchlistLoading } = useWatchlist();
  const addToWatchlist = useAddToWatchlist();
  const removeFromWatchlist = useRemoveFromWatchlist();
  const ingestTicker = useIngestTicker();

  const sectors = useMemo(() => {
    if (!watchlist) return [];
    const unique = new Set(watchlist.map((w) => w.sector).filter(Boolean));
    return Array.from(unique).sort() as string[];
  }, [watchlist]);

  const filteredWatchlist = useMemo(() => {
    if (!watchlist) return [];
    if (!sectorFilter) return watchlist;
    return watchlist.filter((w) => w.sector === sectorFilter);
  }, [watchlist, sectorFilter]);

  async function handleAddTicker(ticker: string) {
    const isInWatchlist = watchlist?.some((w) => w.ticker === ticker);
    if (isInWatchlist) {
      toast.info(`${ticker} is already in your watchlist`);
      return;
    }

    toast.loading(`Fetching data for ${ticker}...`, { id: `ingest-${ticker}` });
    try {
      await ingestTicker.mutateAsync(ticker);
      toast.success(`${ticker} data loaded`, { id: `ingest-${ticker}` });
      addToWatchlist.mutate(ticker);
    } catch {
      toast.error(`Failed to fetch data for ${ticker}`, {
        id: `ingest-${ticker}`,
      });
    }
  }

  return (
    <div className="space-y-8">
      {/* Header + Search */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <TickerSearch onSelect={handleAddTicker} />
      </div>

      {/* Index Cards */}
      <section>
        <SectionHeading>Market Indexes</SectionHeading>
        {indexesLoading ? (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <IndexCardSkeleton key={i} />
            ))}
          </div>
        ) : !indexes?.length ? (
          <p className="text-sm text-muted-foreground">
            No indexes seeded yet. Run{" "}
            <code className="font-mono text-xs">
              uv run python scripts/sync_indexes.py
            </code>{" "}
            to populate.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {indexes.map((idx, i) => (
              <IndexCard
                key={idx.slug}
                name={idx.name}
                slug={idx.slug}
                stockCount={idx.stock_count}
                description={idx.description}
                animationDelay={i * 80}
              />
            ))}
          </div>
        )}
      </section>

      {/* Watchlist */}
      <section>
        <SectionHeading
          action={
            sectors.length > 1 ? (
              <SectorFilter
                sectors={sectors}
                selected={sectorFilter}
                onChange={setSectorFilter}
              />
            ) : undefined
          }
        >
          Watchlist
          {filteredWatchlist.length > 0 && (
            <span className="ml-2 font-normal normal-case text-foreground tracking-normal">
              ({filteredWatchlist.length})
            </span>
          )}
        </SectionHeading>

        {watchlistLoading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <StockCardSkeleton key={i} />
            ))}
          </div>
        ) : filteredWatchlist.length === 0 ? (
          <EmptyState
            icon={StarIcon}
            title="No stocks in your watchlist"
            description="Search for a ticker above to start tracking stocks"
          />
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {filteredWatchlist.map((item, i) => (
              <StockCard
                key={item.ticker}
                ticker={item.ticker}
                name={item.name}
                sector={item.sector}
                score={item.composite_score}
                onRemove={() => removeFromWatchlist.mutate(item.ticker)}
                animationDelay={Math.min(i, 7) * 60}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
