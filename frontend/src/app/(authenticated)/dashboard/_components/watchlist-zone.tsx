"use client";

import { useMemo } from "react";
import { Bookmark, Briefcase } from "lucide-react";
import Link from "next/link";
import { SectionHeading } from "@/components/section-heading";
import { ScoreBadge } from "@/components/score-badge";
import { ScoreBar } from "@/components/score-bar";
import { SignalBadge } from "@/components/signal-badge";
import { ChangeIndicator } from "@/components/change-indicator";
import { EmptyState } from "@/components/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useWatchlist, usePositions, useMarketBriefing } from "@/hooks/use-stocks";
import { MoverRow } from "@/components/mover-row";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";

/** Watchlist cards + Gainers/Losers movers. */
export function WatchlistZone() {
  const { data: watchlist, isLoading } = useWatchlist();
  const { data: positions } = usePositions();
  const { data: briefing } = useMarketBriefing();
  const router = useRouter();
  const heldTickers = useMemo(() => new Set(positions?.map((p) => p.ticker) ?? []), [positions]);
  const movers = briefing?.top_movers;

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
      {/* Watchlist cards */}
      <section className="lg:col-span-3" aria-label="Watchlist">
        <SectionHeading>Watchlist</SectionHeading>

        {isLoading ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-28 rounded-lg bg-card2" />
            ))}
          </div>
        ) : !watchlist?.length ? (
          <EmptyState icon={Bookmark} title="No stocks tracked" description="Search and add stocks to build your watchlist" />
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {watchlist.map((item) => (
              <Link
                key={item.ticker}
                href={`/stocks/${item.ticker}`}
                className="group block rounded-lg border border-border bg-card p-4 transition-all hover:border-primary/30 hover:bg-hov"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-bold">{item.ticker}</span>
                      {heldTickers.has(item.ticker) && (
                        <span className="flex items-center gap-0.5 rounded bg-primary/10 px-1 py-0.5 text-[8px] font-semibold text-primary">
                          <Briefcase className="h-2.5 w-2.5" /> Held
                        </span>
                      )}
                      <ScoreBadge score={item.composite_score} size="xs" />
                    </div>
                    <p className="mt-0.5 text-[10px] text-muted-foreground truncate max-w-[140px]">
                      {item.name ?? "Loading…"}
                    </p>
                  </div>
                </div>

                {item.current_price != null ? (
                  <div className="mt-3 flex items-baseline gap-2">
                    <span className="font-mono text-base font-semibold">
                      ${item.current_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </span>
                    <ChangeIndicator value={item.change_pct} className="text-[10px]" />
                  </div>
                ) : (
                  <p className="mt-3 text-xs text-muted-foreground">Pending ingest…</p>
                )}

                <ScoreBar score={item.composite_score ?? 0} className="mt-2.5" />

                {item.recommendation && (
                  <div className="mt-2 flex items-center justify-between">
                    <SignalBadge signal={item.recommendation} type="recommendation" />
                  </div>
                )}
              </Link>
            ))}
          </div>
        )}
      </section>

      {/* Gainers / Losers sidebar */}
      <section className="lg:col-span-2" aria-label="Top Movers">
        <SectionHeading>Top Movers</SectionHeading>
        {!movers ? (
          <div className="space-y-1">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full rounded-lg bg-card2" />
            ))}
          </div>
        ) : (
          <div className="space-y-3">
            <div>
              <div className="mb-1.5 text-[9px] font-semibold uppercase tracking-wider text-gain">Gainers</div>
              <div className="space-y-1">
                {movers.gainers.length > 0 ? (
                  movers.gainers.slice(0, 3).map((m) => (
                    <MoverRow key={m.ticker} ticker={m.ticker} price={m.current_price} changePct={m.change_pct} macdSignal={m.macd_signal_label} onClick={() => router.push(`/stocks/${m.ticker}`)} />
                  ))
                ) : (
                  <p className="text-xs text-muted-foreground">No gainers today</p>
                )}
              </div>
            </div>
            <div>
              <div className="mb-1.5 text-[9px] font-semibold uppercase tracking-wider text-loss">Losers</div>
              <div className="space-y-1">
                {movers.losers.length > 0 ? (
                  movers.losers.slice(0, 3).map((m) => (
                    <MoverRow key={m.ticker} ticker={m.ticker} price={m.current_price} changePct={m.change_pct} macdSignal={m.macd_signal_label} onClick={() => router.push(`/stocks/${m.ticker}`)} />
                  ))
                ) : (
                  <p className="text-xs text-muted-foreground">No losers today</p>
                )}
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
