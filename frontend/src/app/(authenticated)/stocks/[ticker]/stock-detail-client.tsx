"use client";

import { useState, useMemo } from "react";
import { BarChart3Icon } from "lucide-react";
import {
  useSignals,
  useAddToWatchlist,
  useRemoveFromWatchlist,
  useIsInWatchlist,
  useIngestTicker,
  useStockMeta,
  useFundamentals,
  useDividends,
  useStockNews,
  useStockIntelligence,
  useBenchmark,
  useStockAnalytics,
} from "@/hooks/use-stocks";
import { useForecast } from "@/hooks/use-forecasts";
import { StockHeader } from "@/components/stock-header";
import { SectionNav } from "@/components/section-nav";
import { PriceChart } from "@/components/price-chart";
import { BenchmarkChart } from "@/components/benchmark-chart";
import { SignalCards } from "@/components/signal-cards";
import { SignalHistoryChart } from "@/components/signal-history-chart";
import { RiskReturnCard } from "@/components/risk-return-card";
import { StockAnalyticsCard } from "@/components/stock-analytics-card";
import { FundamentalsCard } from "@/components/fundamentals-card";
import { DividendCard } from "@/components/dividend-card";
import { ForecastCard } from "@/components/forecast-card";
import { IntelligenceCard } from "@/components/intelligence-card";
import { ConvergenceCard } from "@/components/convergence-card";
import { ForecastTrackRecord } from "@/components/forecast-track-record";
import { SentimentCard } from "@/components/sentiment-card";
import { NewsCard } from "@/components/news-card";
import { EmptyState } from "@/components/empty-state";
import { SectionHeading } from "@/components/section-heading";
import { IngestProgressToast } from "@/components/ingest-progress-toast";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import type { PricePeriod } from "@/types/api";
import { PageTransition } from "@/components/motion-primitives";

interface StockDetailClientProps {
  ticker: string;
}

export function StockDetailClient({ ticker }: StockDetailClientProps) {
  const [period, setPeriod] = useState<PricePeriod>("1y");
  const { data: signals, isLoading: signalsLoading } = useSignals(ticker);
  const { name, sector } = useStockMeta(ticker);
  const isInWatchlist = useIsInWatchlist(ticker);
  const addToWatchlist = useAddToWatchlist();
  const removeFromWatchlist = useRemoveFromWatchlist();
  const ingestTicker = useIngestTicker();
  const { data: fundamentals, isLoading: fundLoading } = useFundamentals(ticker);
  const { data: analytics, isLoading: analyticsLoading } = useStockAnalytics(ticker);
  const { data: dividends, isLoading: divLoading } = useDividends(ticker);
  const { data: forecast, isLoading: forecastLoading } = useForecast(ticker);

  // Progressive loading — wait for signals before fetching secondary data
  const hasSignals = !!signals;
  const {
    data: news,
    isLoading: newsLoading,
    isError: newsError,
    refetch: refetchNews,
  } = useStockNews(ticker, hasSignals);
  const {
    data: intelligence,
    isLoading: intelLoading,
    isError: intelError,
    refetch: refetchIntel,
  } = useStockIntelligence(ticker, hasSignals);
  const {
    data: benchmarkData,
    isLoading: benchmarkLoading,
    isError: benchmarkError,
    refetch: refetchBenchmark,
  } = useBenchmark(ticker, period, hasSignals);

  // Extract series names for BenchmarkChart legend
  const benchmarkSeriesNames = useMemo(
    () =>
      benchmarkData?.length
        ? Object.keys(benchmarkData[0]).filter((k) => k !== "date")
        : [],
    [benchmarkData]
  );

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
      await ingestTicker.mutateAsync(ticker);
      toast.dismiss(`ingest-${ticker}`);
      toast.custom(
        (t) => (
          <IngestProgressToast
            ticker={ticker}
            onComplete={() => toast.dismiss(t)}
          />
        ),
        { duration: Infinity, id: `ingest-${ticker}` },
      );
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
    <PageTransition className="space-y-8">

      {signalsLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-8 w-32" />
          <Skeleton className="h-5 w-48" />
        </div>
      ) : (
        <StockHeader
          ticker={ticker}
          name={name}
          sector={sector}
          score={signals?.composite_score ?? null}
          currentPrice={signals?.current_price}
          priceChangePct={signals?.change_pct}
          marketCap={signals?.market_cap}
          isInWatchlist={isInWatchlist}
          onToggleWatchlist={handleToggleWatchlist}
          isRefreshing={signals?.is_refreshing}
          computedAt={signals?.computed_at}
        />
      )}

      <SectionNav />

      <section id="sec-price">
        <PriceChart ticker={ticker} period={period} onPeriodChange={setPeriod} />
      </section>

      <section id="sec-signals">
        <SectionHeading>Signal Breakdown</SectionHeading>
        <SignalCards signals={signals} isLoading={signalsLoading} />
      </section>

      <section id="sec-history">
        <SectionHeading>Signal History (90 days)</SectionHeading>
        <SignalHistoryChart ticker={ticker} />
      </section>

      <section id="sec-convergence">
        <ConvergenceCard ticker={ticker} enabled={hasSignals} />
      </section>

      <section id="sec-benchmark">
        <BenchmarkChart
          data={benchmarkData}
          isLoading={benchmarkLoading}
          isError={benchmarkError}
          onRetry={refetchBenchmark}
          seriesNames={benchmarkSeriesNames}
        />
      </section>

      <section id="sec-risk">
        <RiskReturnCard returns={signals?.returns} />
        <div className="mt-3">
          <StockAnalyticsCard analytics={analytics} isLoading={analyticsLoading} />
        </div>
      </section>

      <section id="sec-fundamentals">
        <FundamentalsCard fundamentals={fundamentals} isLoading={fundLoading} />
      </section>

      <section id="sec-forecast">
        <ForecastCard
          horizons={forecast?.horizons}
          isLoading={forecastLoading}
          currentPrice={undefined}
          modelMape={forecast?.model_mape}
        />
      </section>

      <section id="sec-track-record">
        <ForecastTrackRecord ticker={ticker} enabled={hasSignals} />
      </section>

      <section id="sec-intelligence">
        <IntelligenceCard
          intelligence={intelligence}
          isLoading={intelLoading}
          isError={intelError}
          onRetry={refetchIntel}
        />
      </section>

      <section id="sec-sentiment">
        <SentimentCard ticker={ticker} enabled={hasSignals} />
      </section>

      <section id="sec-news">
        <NewsCard
          news={news}
          isLoading={newsLoading}
          isError={newsError}
          onRetry={refetchNews}
        />
      </section>

      <section id="sec-dividends">
        <DividendCard dividends={dividends} isLoading={divLoading} />
      </section>
    </PageTransition>
  );
}
