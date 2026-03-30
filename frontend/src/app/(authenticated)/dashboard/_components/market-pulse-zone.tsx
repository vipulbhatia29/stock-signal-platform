"use client";

import { Activity, Clock } from "lucide-react";
import { SectionHeading } from "@/components/section-heading";
import { MoverRow } from "@/components/mover-row";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarketBriefing } from "@/hooks/use-stocks";
import { isMarketOpen } from "@/lib/market-hours";
import { cn } from "@/lib/utils";
import { useRouter } from "next/navigation";

/** Zone 1 — Market status + index cards + gainers/losers. */
export function MarketPulseZone() {
  const { data: briefing, isLoading, isError } = useMarketBriefing();
  const router = useRouter();
  const open = isMarketOpen();

  if (isError) {
    return (
      <section aria-label="Market Pulse">
        <SectionHeading>Market Pulse</SectionHeading>
        <p className="text-sm text-muted-foreground">Unable to load market data.</p>
      </section>
    );
  }

  return (
    <section aria-label="Market Pulse">
      <SectionHeading
        action={
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-semibold",
              open ? "bg-gain/10 text-gain" : "bg-muted text-muted-foreground",
            )}
          >
            {open ? <Activity className="h-3 w-3 animate-pulse" /> : <Clock className="h-3 w-3" />}
            {open ? "Market Open" : "Market Closed"}
          </span>
        }
      >
        Market Pulse
      </SectionHeading>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full rounded-lg bg-card2" />
          ))}
        </div>
      ) : (
        <>
          {/* Index performance row */}
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            {briefing?.indexes.map((idx) => (
              <div
                key={idx.ticker}
                className="flex items-center justify-between rounded-lg border border-border/30 bg-[rgba(15,23,42,0.5)] p-3"
              >
                <div>
                  <div className="text-[11px] text-muted-foreground">{idx.name}</div>
                  <div className="text-sm font-bold">${idx.price.toLocaleString()}</div>
                </div>
                <span className={cn("text-sm font-bold", idx.change_pct >= 0 ? "text-[var(--gain)]" : "text-[var(--loss)]")}>
                  {idx.change_pct >= 0 ? "+" : ""}{idx.change_pct.toFixed(2)}%
                </span>
              </div>
            ))}
          </div>

          {/* Gainers / Losers split */}
          {briefing?.top_movers && (
            <div className="mt-3 grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <div className="mb-1.5 text-[9px] font-semibold uppercase tracking-wider text-[var(--gain)]">Gainers</div>
                <div className="space-y-1">
                  {briefing.top_movers.gainers.slice(0, 4).map((m) => (
                    <MoverRow key={m.ticker} ticker={m.ticker} price={m.current_price} changePct={m.change_pct} macdSignal={m.macd_signal_label} onClick={() => router.push(`/stocks/${m.ticker}`)} />
                  ))}
                </div>
              </div>
              <div>
                <div className="mb-1.5 text-[9px] font-semibold uppercase tracking-wider text-[var(--loss)]">Losers</div>
                <div className="space-y-1">
                  {briefing.top_movers.losers.slice(0, 4).map((m) => (
                    <MoverRow key={m.ticker} ticker={m.ticker} price={m.current_price} changePct={m.change_pct} macdSignal={m.macd_signal_label} onClick={() => router.push(`/stocks/${m.ticker}`)} />
                  ))}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
