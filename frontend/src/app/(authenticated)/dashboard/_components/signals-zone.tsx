"use client";

import { useMemo } from "react";
import { Zap, TrendingUp, TrendingDown } from "lucide-react";
import { SectionHeading } from "@/components/section-heading";
import { RecommendationRow } from "@/components/recommendation-row";
import { EmptyState } from "@/components/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useRecommendations, usePositions, useTrendingStocks } from "@/hooks/use-stocks";
import { ScoreBadge } from "@/components/score-badge";
import { cn } from "@/lib/utils";
import Link from "next/link";

/** Zone 2 — Your Signals (recommendations) + Top Movers (trending). */
export function SignalsZone() {
  const { data: recommendations, isLoading: recsLoading } = useRecommendations();
  const { data: positions } = usePositions();
  const { data: trending, isLoading: trendingLoading } = useTrendingStocks(6);

  const heldTickers = useMemo(() => {
    if (!positions) return new Set<string>();
    return new Set(positions.map((p) => p.ticker));
  }, [positions]);

  // Build reasoning text from recommendation
  const getReasoningText = (rec: {
    action: string;
    composite_score: number;
    reasoning?: Record<string, unknown> | null;
  }): string => {
    if (
      rec.reasoning &&
      typeof rec.reasoning === "object" &&
      "summary" in rec.reasoning
    ) {
      return String(rec.reasoning.summary);
    }
    const score = rec.composite_score.toFixed(1);
    if (rec.action === "BUY")
      return `Strong signals with composite score ${score}. Consider adding to portfolio.`;
    if (rec.action === "WATCH")
      return `Mixed signals — composite score ${score}. Monitor for entry point.`;
    if (rec.action === "AVOID")
      return `Weak signals with composite score ${score}. High risk indicators.`;
    if (rec.action === "SELL")
      return `Bearish across indicators. Score ${score}. Consider reducing exposure.`;
    return `Composite score ${score}. Hold current position.`;
  };

  // Split trending into gainers (high score) and losers (low score)
  const movers = useMemo(() => {
    if (!trending?.items) return { gainers: [], losers: [] };
    const sorted = [...trending.items].sort(
      (a, b) => (b.composite_score ?? 0) - (a.composite_score ?? 0)
    );
    return {
      gainers: sorted.filter((s) => (s.composite_score ?? 0) >= 5).slice(0, 3),
      losers: sorted.filter((s) => (s.composite_score ?? 0) < 5).slice(0, 3),
    };
  }, [trending]);

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
      {/* Zone 2a: Your Signals — 3 cols */}
      <section className="lg:col-span-3">
        <SectionHeading>
          <span className="inline-flex items-center gap-1.5">
            <Zap className="h-3 w-3 text-warning" />
            Your Signals
          </span>
        </SectionHeading>

        {recsLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full rounded-lg bg-card2" />
            ))}
          </div>
        ) : !recommendations?.length ? (
          <EmptyState
            icon={Zap}
            title="No signals yet"
            description="Add stocks to your watchlist and we'll generate buy/sell/watch signals"
          />
        ) : (
          <div className="space-y-2">
            {recommendations.slice(0, 5).map((rec) => (
              <RecommendationRow
                key={rec.ticker}
                ticker={rec.ticker}
                action={rec.action}
                confidence={rec.confidence}
                compositeScore={rec.composite_score}
                reasoning={getReasoningText(rec)}
                isHeld={heldTickers.has(rec.ticker)}
              />
            ))}
          </div>
        )}
      </section>

      {/* Zone 2b: Top Movers — 2 cols */}
      <section className="lg:col-span-2">
        <SectionHeading>Top Movers</SectionHeading>

        {trendingLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full rounded-lg bg-card2" />
            ))}
          </div>
        ) : (
          <div className="space-y-3">
            {/* Gainers */}
            {movers.gainers.length > 0 && (
              <div>
                <div className="mb-1.5 flex items-center gap-1 text-[9px] font-semibold uppercase tracking-wider text-gain">
                  <TrendingUp className="h-3 w-3" /> Gainers
                </div>
                <div className="space-y-1">
                  {movers.gainers.map((s) => (
                    <MoverItem key={s.ticker} ticker={s.ticker} name={s.name} score={s.composite_score} direction="up" />
                  ))}
                </div>
              </div>
            )}

            {/* Losers */}
            {movers.losers.length > 0 && (
              <div>
                <div className="mb-1.5 flex items-center gap-1 text-[9px] font-semibold uppercase tracking-wider text-loss">
                  <TrendingDown className="h-3 w-3" /> Losers
                </div>
                <div className="space-y-1">
                  {movers.losers.map((s) => (
                    <MoverItem key={s.ticker} ticker={s.ticker} name={s.name} score={s.composite_score} direction="down" />
                  ))}
                </div>
              </div>
            )}

            {movers.gainers.length === 0 && movers.losers.length === 0 && (
              <p className="text-sm text-muted-foreground">
                No mover data available.
              </p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

/** Compact row for a top mover stock. */
function MoverItem({
  ticker,
  name,
  score,
  direction,
}: {
  ticker: string;
  name: string;
  score: number | null;
  direction: "up" | "down";
}) {
  return (
    <Link
      href={`/stocks/${ticker}`}
      className={cn(
        "flex items-center justify-between rounded-lg border border-border bg-card px-3 py-2",
        "transition-colors hover:border-[var(--bhi)] hover:bg-hov"
      )}
    >
      <div className="min-w-0 flex-1">
        <span className="font-mono text-xs font-bold">{ticker}</span>
        <span className="ml-2 truncate text-[10px] text-muted-foreground">
          {name}
        </span>
      </div>
      <ScoreBadge score={score} size="xs" />
    </Link>
  );
}
