"use client";

import { Suspense, useCallback, useMemo, useState } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { FilterIcon, AlignJustifyIcon, LayoutListIcon, LayoutGridIcon } from "lucide-react";
import { useIndexes, useBulkSignals, useWatchlist } from "@/hooks/use-stocks";
import {
  ScreenerFilters,
  type FilterValues,
} from "@/components/screener-filters";
import { ScreenerTable, type TabKey } from "@/components/screener-table";
import { ScreenerGrid } from "@/components/screener-grid";
import { PaginationControls } from "@/components/pagination-controls";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { DensityProvider, useDensity } from "@/lib/density-context";
import { PageTransition } from "@/components/motion-primitives";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 50;

export default function ScreenerPage() {
  return (
    <DensityProvider>
      <Suspense>
        <ScreenerContent />
      </Suspense>
    </DensityProvider>
  );
}

function ViewModeToggle({
  viewMode,
  onChange,
}: {
  viewMode: "table" | "grid";
  onChange: (mode: "table" | "grid") => void;
}) {
  return (
    <Button
      variant="ghost"
      size="sm"
      className="h-8 w-8 p-0"
      onClick={() => onChange(viewMode === "table" ? "grid" : "table")}
      aria-label={`Switch to ${viewMode === "table" ? "grid" : "table"} view`}
    >
      {viewMode === "table" ? (
        <LayoutGridIcon className="size-4" />
      ) : (
        <LayoutListIcon className="size-4" />
      )}
    </Button>
  );
}

function DensityToggle() {
  const { density, toggleDensity } = useDensity();
  return (
    <Button
      variant="ghost"
      size="sm"
      className="h-8 w-8 p-0"
      onClick={toggleDensity}
      aria-label={`Switch to ${density === "comfortable" ? "compact" : "comfortable"} density`}
    >
      {density === "comfortable" ? (
        <AlignJustifyIcon className="size-4" />
      ) : (
        <LayoutListIcon className="size-4" />
      )}
    </Button>
  );
}

type ScreenerTab = "all" | "watchlist";

function ScreenerContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const { data: indexes } = useIndexes();
  const { data: watchlist } = useWatchlist();
  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const [viewMode, setViewMode] = useState<"table" | "grid">("table");

  const screenerTab: ScreenerTab =
    searchParams.get("tab") === "watchlist" ? "watchlist" : "all";

  const watchlistTickers = useMemo(
    () => new Set(watchlist?.map((w) => w.ticker) ?? []),
    [watchlist]
  );
  const watchlistCount = watchlistTickers.size;

  const filters: FilterValues = useMemo(
    () => ({
      index: searchParams.get("index"),
      rsiState: searchParams.get("rsi"),
      macdState: searchParams.get("macd"),
      sector: searchParams.get("sector"),
      scoreMin: Number(searchParams.get("score_min") ?? 0),
      scoreMax: Number(searchParams.get("score_max") ?? 10),
    }),
    [searchParams]
  );

  const sortBy = searchParams.get("sort") ?? "composite_score";
  const sortOrder =
    (searchParams.get("order") as "asc" | "desc") ?? "desc";
  const page = Number(searchParams.get("page") ?? 0);

  const updateParams = useCallback(
    (updates: Record<string, string | null>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(updates)) {
        if (value === null || value === "") {
          params.delete(key);
        } else {
          params.set(key, value);
        }
      }
      router.replace(`${pathname}?${params.toString()}`);
    },
    [searchParams, router, pathname]
  );

  function handleFiltersChange(newFilters: FilterValues) {
    updateParams({
      index: newFilters.index,
      rsi: newFilters.rsiState,
      macd: newFilters.macdState,
      sector: newFilters.sector,
      score_min:
        newFilters.scoreMin === 0 ? null : String(newFilters.scoreMin),
      score_max:
        newFilters.scoreMax === 10 ? null : String(newFilters.scoreMax),
      page: null,
    });
  }

  function handleSort(column: string) {
    if (column === sortBy) {
      updateParams({ order: sortOrder === "asc" ? "desc" : "asc" });
    } else {
      updateParams({ sort: column, order: "desc" });
    }
  }

  function handlePageChange(newPage: number) {
    updateParams({ page: newPage === 0 ? null : String(newPage) });
  }

  function setScreenerTab(tab: ScreenerTab) {
    updateParams({ tab: tab === "all" ? null : tab, page: null });
  }

  const { data, isLoading } = useBulkSignals({
    index: filters.index ?? undefined,
    rsi_state: filters.rsiState ?? undefined,
    macd_state: filters.macdState ?? undefined,
    sector: filters.sector ?? undefined,
    score_min: filters.scoreMin,
    score_max: filters.scoreMax,
    sort_by: sortBy,
    sort_order: sortOrder,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  });

  const displayItems = useMemo(() => {
    const items = data?.items ?? [];
    if (screenerTab === "watchlist") {
      return items.filter((item) => watchlistTickers.has(item.ticker));
    }
    return items;
  }, [data?.items, screenerTab, watchlistTickers]);

  const displayTotal =
    screenerTab === "watchlist" ? displayItems.length : (data?.total ?? 0);

  return (
    <PageTransition className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Screener</h1>
        <div className="flex items-center gap-1">
          {viewMode === "table" && <DensityToggle />}
          <ViewModeToggle viewMode={viewMode} onChange={setViewMode} />
        </div>
      </div>

      {/* Screener tab bar: All Stocks | Watchlist */}
      <div className="flex gap-1 rounded-lg bg-[rgba(15,23,42,0.5)] p-1 w-fit">
        <button
          className={cn(
            "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
            screenerTab === "all"
              ? "bg-primary/15 text-primary"
              : "text-muted-foreground hover:text-foreground"
          )}
          onClick={() => setScreenerTab("all")}
        >
          All Stocks
        </button>
        <button
          className={cn(
            "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
            screenerTab === "watchlist"
              ? "bg-primary/15 text-primary"
              : "text-muted-foreground hover:text-foreground"
          )}
          onClick={() => setScreenerTab("watchlist")}
        >
          Watchlist
          {watchlistCount > 0 && (
            <span className="ml-1 rounded-full bg-primary/20 px-1.5 text-xs">
              {watchlistCount}
            </span>
          )}
        </button>
      </div>

      <ScreenerFilters
        filters={filters}
        onChange={handleFiltersChange}
        indexes={indexes ?? []}
      />

      {!isLoading && displayItems.length === 0 ? (
        <EmptyState
          icon={FilterIcon}
          title={
            screenerTab === "watchlist"
              ? "No watchlisted stocks"
              : "No stocks match your filters"
          }
          description={
            screenerTab === "watchlist"
              ? "Add stocks to your watchlist from the stock detail page"
              : "Try broadening your search criteria"
          }
        />
      ) : viewMode === "grid" ? (
        <ScreenerGrid items={displayItems} isLoading={isLoading} />
      ) : (
        <ScreenerTable
          items={displayItems}
          sortBy={sortBy}
          sortOrder={sortOrder}
          onSort={handleSort}
          isLoading={isLoading}
          activeTab={activeTab}
          onTabChange={setActiveTab}
        />
      )}
      {displayTotal > PAGE_SIZE && (
        <PaginationControls
          page={page}
          pageSize={PAGE_SIZE}
          total={displayTotal}
          onPageChange={handlePageChange}
        />
      )}
    </PageTransition>
  );
}
