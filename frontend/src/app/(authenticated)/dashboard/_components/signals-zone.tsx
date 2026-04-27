"use client";

import { useMemo } from "react";
import { Zap } from "lucide-react";
import { SectionHeading } from "@/components/section-heading";
import { SignalStockCard } from "@/components/signal-stock-card";
import { MoverRow } from "@/components/mover-row";
import { EmptyState } from "@/components/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useWatchlist, useMarketBriefing } from "@/hooks/use-stocks";
import type { MetricChip } from "@/components/metrics-strip";
import type { WatchlistItem } from "@/types/api";
import { useRouter } from "next/navigation";

function buildWatchlistMetrics(item: WatchlistItem): MetricChip[] {
  const chips: MetricChip[] = [];
  if (item.rsi_value != null) {
    const rsiRound = Math.round(item.rsi_value);
    chips.push({
      label: "RSI",
      value: rsiRound.toString(),
      sentiment: rsiRound < 30 ? "positive" : rsiRound > 70 ? "negative" : "neutral",
    });
  }
  if (item.macd_signal_label) {
    chips.push({
      label: "MACD",
      value: item.macd_signal_label,
      sentiment: item.macd_signal_label.includes("bullish") ? "positive" : item.macd_signal_label.includes("bearish") ? "negative" : "neutral",
    });
  }
  if (item.change_pct != null) {
    chips.push({
      label: "Chg",
      value: `${item.change_pct >= 0 ? "+" : ""}${item.change_pct.toFixed(2)}%`,
      sentiment: item.change_pct > 0 ? "positive" : item.change_pct < 0 ? "negative" : "neutral",
    });
  }
  return chips;
}

/** Zone 2 — Signal cards from watchlist + top movers side panel. */
export function SignalsZone() {
  const { data: watchlist, isLoading: watchlistLoading } = useWatchlist();
  const { data: briefing } = useMarketBriefing();
  const router = useRouter();

  const watchlistWithSignals = useMemo(() => {
    if (!watchlist) return [];
    return watchlist.filter((item) => item.composite_score != null);
  }, [watchlist]);

  const watchlistPending = useMemo(() => {
    if (!watchlist) return [];
    return watchlist.filter((item) => item.composite_score == null);
  }, [watchlist]);

  const movers = briefing?.top_movers;

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
      <section className="lg:col-span-3" aria-label="Your Signals">
        <SectionHeading>
          <span className="inline-flex items-center gap-1.5">
            <Zap className="h-3 w-3 text-warning" />
            Your Signals
          </span>
        </SectionHeading>

        {watchlistLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-24 w-full rounded-lg bg-card2" />
            ))}
          </div>
        ) : !watchlist?.length ? (
          <EmptyState icon={Zap} title="No signals yet" description="Add stocks to your watchlist to see signals" />
        ) : (
          <>
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
              {watchlistWithSignals.map((item) => (
                <SignalStockCard
                  key={item.ticker}
                  ticker={item.ticker}
                  name={item.name}
                  compositeScore={item.composite_score ?? 0}
                  action={item.recommendation ?? "—"}
                  metrics={buildWatchlistMetrics(item)}
                  onClick={() => router.push(`/stocks/${item.ticker}`)}
                />
              ))}
            </div>
            {watchlistPending.length > 0 && (
              <div className="mt-2 space-y-1">
                {watchlistPending.map((item) => (
                  <div
                    key={item.ticker}
                    className="flex items-center justify-between rounded-lg border border-border/20 bg-muted/20 px-3 py-2 text-xs cursor-pointer hover:bg-muted/30 transition-colors"
                    onClick={() => router.push(`/stocks/${item.ticker}`)}
                  >
                    <span className="font-medium">{item.ticker}</span>
                    <span className="text-muted-foreground">Pending ingest…</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </section>

      <section className="lg:col-span-2" aria-label="Top Movers">
        <SectionHeading>Top Movers</SectionHeading>
        {!movers ? (
          <div className="space-y-1">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full rounded-lg bg-card2" />
            ))}
          </div>
        ) : (
          <div className="space-y-1">
            {[...movers.gainers.slice(0, 3), ...movers.losers.slice(0, 3)].map((m, i) => (
              <MoverRow key={`${m.ticker}-${i}`} ticker={m.ticker} price={m.current_price} changePct={m.change_pct} macdSignal={m.macd_signal_label} onClick={() => router.push(`/stocks/${m.ticker}`)} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
