"use client";

import { useState, useCallback } from "react";
import {
  PageTransition,
  StaggerGroup,
  StaggerItem,
} from "@/components/motion-primitives";
import { SectorAccordion } from "@/components/sector-accordion";
import { SectorStocksTable } from "@/components/sector-stocks-table";
import { CorrelationHeatmap } from "@/components/correlation-heatmap";
import { CorrelationTable } from "@/components/correlation-table";
import { CorrelationTickerChips } from "@/components/correlation-ticker-chips";
import {
  useSectors,
  useSectorStocks,
  useSectorCorrelation,
} from "@/hooks/use-sectors";
import { usePortfolioSummary } from "@/hooks/use-stocks";
import { AllocationDonut, DONUT_COLORS } from "@/components/allocation-donut";
import { SectionHeading } from "@/components/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import type { SectorScope } from "@/types/api";

export function SectorsClient() {
  const [scope, setScope] = useState<SectorScope>("all");
  const [openSector, setOpenSector] = useState<string | null>(null);
  const [correlationTickers, setCorrelationTickers] = useState<string[]>([]);

  const { data: sectorsData, isLoading: sectorsLoading } = useSectors(scope);
  const { data: stocksData, isLoading: stocksLoading } =
    useSectorStocks(openSector);
  const { data: correlationData } = useSectorCorrelation(
    openSector,
    correlationTickers.length >= 2 ? correlationTickers : null
  );
  const { data: portfolioSummary } = usePortfolioSummary();

  const sectors = sectorsData?.sectors ?? [];

  const handleToggle = useCallback(
    (sector: string) => {
      if (openSector === sector) {
        setOpenSector(null);
        setCorrelationTickers([]);
      } else {
        setOpenSector(sector);
        setCorrelationTickers([]);
      }
    },
    [openSector]
  );

  const handleAddToCorrelation = useCallback(
    (ticker: string) => {
      if (correlationTickers.length >= 15) return;
      if (!correlationTickers.includes(ticker)) {
        setCorrelationTickers((prev) => [...prev, ticker]);
      }
    },
    [correlationTickers]
  );

  const handleRemoveFromCorrelation = useCallback((ticker: string) => {
    setCorrelationTickers((prev) => prev.filter((t) => t !== ticker));
  }, []);

  // Build allocation donut data from portfolio summary
  const donutAllocations =
    portfolioSummary?.sectors?.map((s, i) => ({
      sector: s.sector,
      pct: s.pct,
      color: DONUT_COLORS[i % DONUT_COLORS.length],
    })) ?? [];

  return (
    <PageTransition>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <SectionHeading>Sector Performance</SectionHeading>
          <ScopeToggle scope={scope} onChange={setScope} />
        </div>

        {/* Allocation overview (portfolio scope only) */}
        {scope !== "watchlist" && donutAllocations.length > 0 && (
          <div className="flex justify-center">
            <AllocationDonut
              allocations={donutAllocations}
              stockCount={portfolioSummary?.position_count}
            />
          </div>
        )}

        {/* Sector accordions */}
        {sectorsLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-14 rounded-lg" />
            ))}
          </div>
        ) : sectors.length === 0 ? (
          <p className="text-center text-subtle py-8">
            No sectors found. Add stocks to your watchlist or portfolio.
          </p>
        ) : (
          <StaggerGroup>
            {sectors.map((sector) => (
              <StaggerItem key={sector.sector}>
                <SectorAccordion
                  sector={sector}
                  isOpen={openSector === sector.sector}
                  onToggle={() => handleToggle(sector.sector)}
                >
                  <SectorAccordionContent
                    stocks={stocksData?.stocks ?? []}
                    stocksLoading={stocksLoading && openSector === sector.sector}
                    correlationTickers={correlationTickers}
                    correlationData={correlationData ?? null}
                    onAddToCorrelation={handleAddToCorrelation}
                    onRemoveFromCorrelation={handleRemoveFromCorrelation}
                  />
                </SectorAccordion>
              </StaggerItem>
            ))}
          </StaggerGroup>
        )}
      </div>
    </PageTransition>
  );
}

// ── Scope Toggle ─────────────────────────────────────────────────────────────

function ScopeToggle({
  scope,
  onChange,
}: {
  scope: SectorScope;
  onChange: (scope: SectorScope) => void;
}) {
  const options: { value: SectorScope; label: string }[] = [
    { value: "all", label: "All" },
    { value: "portfolio", label: "Portfolio" },
    { value: "watchlist", label: "Watchlist" },
  ];

  return (
    <div className="flex rounded-md border border-border overflow-hidden">
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          className={`px-3 py-1.5 text-xs font-medium transition-colors ${
            scope === opt.value
              ? "bg-primary text-primary-foreground"
              : "bg-card text-subtle hover:bg-muted/30"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

// ── Accordion Content ────────────────────────────────────────────────────────

function SectorAccordionContent({
  stocks,
  stocksLoading,
  correlationTickers,
  correlationData,
  onAddToCorrelation,
  onRemoveFromCorrelation,
}: {
  stocks: import("@/types/api").SectorStock[];
  stocksLoading: boolean;
  correlationTickers: string[];
  correlationData: import("@/types/api").CorrelationData | null;
  onAddToCorrelation: (ticker: string) => void;
  onRemoveFromCorrelation: (ticker: string) => void;
}) {
  if (stocksLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Stocks table */}
      <SectorStocksTable
        stocks={stocks}
        onTickerClick={onAddToCorrelation}
      />

      {/* Correlation section */}
      {correlationTickers.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-xs font-medium text-subtle uppercase tracking-wider">
            Correlation Analysis
          </h4>

          <CorrelationTickerChips
            tickers={correlationTickers}
            onRemove={onRemoveFromCorrelation}
            excludedTickers={correlationData?.excluded_tickers}
          />

          {correlationData && correlationData.tickers.length >= 2 && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <CorrelationHeatmap
                tickers={correlationData.tickers}
                matrix={correlationData.matrix}
              />
              <CorrelationTable
                tickers={correlationData.tickers}
                matrix={correlationData.matrix}
              />
            </div>
          )}

          {correlationTickers.length < 2 && (
            <p className="text-xs text-subtle">
              Click on stocks above to add them to the correlation analysis
              (minimum 2).
            </p>
          )}
        </div>
      )}
    </div>
  );
}
