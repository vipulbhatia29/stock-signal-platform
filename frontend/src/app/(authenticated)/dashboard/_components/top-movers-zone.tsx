"use client";

import { SectionHeading } from "@/components/section-heading";
import { MoverRow } from "@/components/mover-row";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarketBriefing } from "@/hooks/use-stocks";
import { useRouter } from "next/navigation";

/** Top Movers — gainers and losers side by side, full width. */
export function TopMoversZone() {
  const { data: briefing } = useMarketBriefing();
  const router = useRouter();
  const movers = briefing?.top_movers;

  return (
    <section aria-label="Top Movers">
      <SectionHeading>Top Movers</SectionHeading>

      {!movers ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="space-y-1">
              {Array.from({ length: 3 }).map((_, j) => (
                <Skeleton key={j} className="h-10 w-full rounded-lg bg-card2" />
              ))}
            </div>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div>
            <div className="mb-1.5 text-[9px] font-semibold uppercase tracking-wider text-gain">Gainers</div>
            <div className="space-y-1">
              {movers.gainers.length > 0 ? (
                movers.gainers.slice(0, 4).map((m) => (
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
                movers.losers.slice(0, 4).map((m) => (
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
  );
}
