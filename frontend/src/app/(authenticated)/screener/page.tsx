"use client";

import { Suspense, useCallback, useMemo } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { FilterIcon } from "lucide-react";
import { useIndexes, useBulkSignals } from "@/hooks/use-stocks";
import {
  ScreenerFilters,
  type FilterValues,
} from "@/components/screener-filters";
import { ScreenerTable } from "@/components/screener-table";
import { PaginationControls } from "@/components/pagination-controls";
import { EmptyState } from "@/components/empty-state";

const PAGE_SIZE = 50;

export default function ScreenerPage() {
  return (
    <Suspense>
      <ScreenerContent />
    </Suspense>
  );
}

function ScreenerContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const { data: indexes } = useIndexes();

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

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">Screener</h1>

      <ScreenerFilters
        filters={filters}
        onChange={handleFiltersChange}
        indexes={indexes ?? []}
      />

      {!isLoading && data && data.items.length === 0 ? (
        <EmptyState
          icon={FilterIcon}
          title="No stocks match your filters"
          description="Try broadening your search criteria"
        />
      ) : (
        <>
          <ScreenerTable
            items={data?.items ?? []}
            sortBy={sortBy}
            sortOrder={sortOrder}
            onSort={handleSort}
            isLoading={isLoading}
          />
          {data && data.total > 0 && (
            <PaginationControls
              page={page}
              pageSize={PAGE_SIZE}
              total={data.total}
              onPageChange={handlePageChange}
            />
          )}
        </>
      )}
    </div>
  );
}
