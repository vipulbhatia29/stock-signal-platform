"use client";

import { useState } from "react";
import { BarChart3Icon } from "lucide-react";
import {
  useSignals,
  useAddToWatchlist,
  useRemoveFromWatchlist,
  useIsInWatchlist,
  useIngestTicker,
} from "@/hooks/use-stocks";
import { StockHeader } from "@/components/stock-header";
import { PriceChart } from "@/components/price-chart";
import { SignalCards } from "@/components/signal-cards";
import { SignalHistoryChart } from "@/components/signal-history-chart";
import { RiskReturnCard } from "@/components/risk-return-card";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import type { PricePeriod } from "@/types/api";

interface StockDetailClientProps {
  ticker: string;
}

export function StockDetailClient({ ticker }: StockDetailClientProps) {
  const [period, setPeriod] = useState<PricePeriod>("1y");
  const { data: signals, isLoading: signalsLoading } = useSignals(ticker);
  const isInWatchlist = useIsInWatchlist(ticker);
  const addToWatchlist = useAddToWatchlist();
  const removeFromWatchlist = useRemoveFromWatchlist();
  const ingestTicker = useIngestTicker();

  function handleToggleWatchlist() {
    if (isInWatchlist) {
      removeFromWatchlist.mutate(ticker);
    } else {
      addToWatchlist.mutate(ticker);
    }
  }

  async function handleIngest() {
    toast.loading(`Fetching data for ${ticker}...`, {
      id: `ingest-${ticker}`,
    });
    try {
      const result = await ingestTicker.mutateAsync(ticker);
      toast.success(`${result.rows_fetched} data points loaded`, {
        id: `ingest-${ticker}`,
      });
    } catch {
      toast.error(`Failed to fetch data for ${ticker}`, {
        id: `ingest-${ticker}`,
      });
    }
  }

  // Show ingest prompt if no signals exist
  if (!signalsLoading && !signals) {
    return (
      <div className="space-y-6">
        <h1 className="font-mono text-2xl font-bold">{ticker}</h1>
        <EmptyState
          icon={BarChart3Icon}
          title="No signals available"
          description="This stock hasn't been analyzed yet"
          action={
            <Button onClick={handleIngest} disabled={ingestTicker.isPending}>
              {ingestTicker.isPending ? "Loading..." : "Run Analysis"}
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {signalsLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-8 w-32" />
          <Skeleton className="h-5 w-48" />
        </div>
      ) : (
        <StockHeader
          ticker={ticker}
          name={null}
          sector={null}
          score={signals?.composite_score ?? null}
          isInWatchlist={isInWatchlist}
          onToggleWatchlist={handleToggleWatchlist}
        />
      )}

      <section>
        <PriceChart ticker={ticker} period={period} onPeriodChange={setPeriod} />
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wider text-muted-foreground">
          Signal Breakdown
        </h2>
        <SignalCards signals={signals} isLoading={signalsLoading} />
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wider text-muted-foreground">
          Signal History (90 days)
        </h2>
        <SignalHistoryChart ticker={ticker} />
      </section>

      <section>
        <RiskReturnCard returns={signals?.returns} />
      </section>
    </div>
  );
}
