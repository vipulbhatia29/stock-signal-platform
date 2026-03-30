"use client";

import { useMemo } from "react";
import { Zap } from "lucide-react";
import { SectionHeading } from "@/components/section-heading";
import { SignalStockCard } from "@/components/signal-stock-card";
import { MoverRow } from "@/components/mover-row";
import { EmptyState } from "@/components/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useRecommendations, useBulkSignalsByTickers, useMarketBriefing } from "@/hooks/use-stocks";
import { buildSignalReason } from "@/lib/signal-reason";
import type { MetricChip } from "@/components/metrics-strip";
import type { BulkSignalItem } from "@/types/api";
import { useRouter } from "next/navigation";

function buildMetrics(s: BulkSignalItem): MetricChip[] {
  const chips: MetricChip[] = [];
  if (s.rsi_value != null) chips.push({ label: "RSI", value: Math.round(s.rsi_value).toString(), sentiment: s.rsi_signal === "oversold" ? "positive" : s.rsi_signal === "overbought" ? "negative" : "neutral" });
  if (s.macd_signal) chips.push({ label: "MACD", value: s.macd_signal, sentiment: s.macd_signal.includes("bullish") ? "positive" : s.macd_signal.includes("bearish") ? "negative" : "neutral" });
  if (s.sharpe_ratio != null) chips.push({ label: "Sharpe", value: s.sharpe_ratio.toFixed(2), sentiment: s.sharpe_ratio >= 1 ? "positive" : s.sharpe_ratio < 0 ? "negative" : "warning" });
  if (s.sma_signal) chips.push({ label: "SMA", value: s.sma_signal, sentiment: s.sma_signal === "golden_cross" || s.sma_signal === "above" ? "positive" : "negative" });
  return chips;
}

/** Zone 2 — Signal cards + top movers side panel. */
export function SignalsZone() {
  const { data: recs, isLoading: recsLoading } = useRecommendations();
  const { data: briefing } = useMarketBriefing();
  const router = useRouter();

  const recTickers = useMemo(() => {
    if (!recs) return [];
    return recs
      .filter((r) => r.action === "BUY" || r.action === "STRONG_BUY")
      .slice(0, 6)
      .map((r) => r.ticker);
  }, [recs]);

  const { data: bulkSignals, isLoading: signalsLoading } = useBulkSignalsByTickers(recTickers, recTickers.length > 0);
  const isLoading = recsLoading || signalsLoading;

  const signalMap = useMemo(() => {
    const m = new Map<string, BulkSignalItem>();
    bulkSignals?.items.forEach((s) => m.set(s.ticker, s));
    return m;
  }, [bulkSignals]);

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

        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-24 w-full rounded-lg bg-card2" />
            ))}
          </div>
        ) : !recTickers.length ? (
          <EmptyState icon={Zap} title="No signals yet" description="Add stocks and we'll generate buy/sell/watch signals" />
        ) : (
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            {recTickers.map((ticker) => {
              const rec = recs?.find((r) => r.ticker === ticker);
              const sig = signalMap.get(ticker);
              return (
                <SignalStockCard
                  key={ticker}
                  ticker={ticker}
                  name={sig?.name}
                  compositeScore={rec?.composite_score ?? 0}
                  action={rec?.action ?? "WATCH"}
                  metrics={sig ? buildMetrics(sig) : []}
                  reason={sig ? buildSignalReason(sig) : undefined}
                  onClick={() => router.push(`/stocks/${ticker}`)}
                />
              );
            })}
          </div>
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
            {[...movers.gainers.slice(0, 3), ...movers.losers.slice(0, 3)].map((m) => (
              <MoverRow key={m.ticker} ticker={m.ticker} price={m.current_price} changePct={m.change_pct} macdSignal={m.macd_signal_label} onClick={() => router.push(`/stocks/${m.ticker}`)} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
