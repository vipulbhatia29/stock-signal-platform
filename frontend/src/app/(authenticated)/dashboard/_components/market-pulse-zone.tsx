"use client";

import { Activity, Clock } from "lucide-react";
import { SectionHeading } from "@/components/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarketBriefing } from "@/hooks/use-stocks";
import { useMacroSentiment } from "@/hooks/use-sentiment";
import { isMarketOpen } from "@/lib/market-hours";
import { cn } from "@/lib/utils";

/** Market Indexes — 3-4 index cards with price + change. */
export function MarketPulseZone() {
  const { data: briefing, isLoading, isError } = useMarketBriefing();
  const { data: macroData } = useMacroSentiment(7);
  const latestMacro = macroData?.data?.[macroData.data.length - 1];
  const open = isMarketOpen();

  if (isError) {
    return (
      <section aria-label="Market Indexes">
        <SectionHeading>Market Indexes</SectionHeading>
        <p className="text-sm text-muted-foreground">Unable to load market data.</p>
      </section>
    );
  }

  return (
    <section aria-label="Market Indexes">
      <SectionHeading
        action={
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-semibold",
                open ? "bg-gain/10 text-gain" : "bg-muted text-muted-foreground",
              )}
            >
              {open ? <Activity className="h-3 w-3 animate-pulse" /> : <Clock className="h-3 w-3" />}
              {open ? "Market Open" : "Market Closed"}
            </span>
            {latestMacro && (
              <span className={cn(
                "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[10px] font-semibold",
                latestMacro.macro_sentiment > 0.2 ? "bg-gain/10 text-gain" :
                latestMacro.macro_sentiment < -0.2 ? "bg-loss/10 text-loss" :
                "bg-muted text-muted-foreground"
              )}>
                {latestMacro.macro_sentiment > 0.2 ? "▲ Bullish" :
                 latestMacro.macro_sentiment < -0.2 ? "▼ Bearish" : "— Neutral"}
              </span>
            )}
          </div>
        }
      >
        Market Indexes
      </SectionHeading>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full rounded-lg bg-card2" />
          ))}
        </div>
      ) : (
        <IndexCards indexes={briefing?.indexes ?? []} />
      )}
    </section>
  );
}

// Always render S&P 500, NASDAQ, Dow — fill from API data, fallback to "—"
const REQUIRED_INDEXES = [
  { ticker: "^GSPC", name: "S&P 500" },
  { ticker: "^IXIC", name: "NASDAQ" },
  { ticker: "^DJI", name: "Dow 30" },
] as const;

function IndexCards({ indexes }: { indexes: { ticker: string; name: string; price: number; change_pct: number }[] }) {
  const indexMap = new Map(indexes.map((idx) => [idx.ticker, idx]));

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
      {REQUIRED_INDEXES.map(({ ticker, name }) => {
        const data = indexMap.get(ticker);
        return (
          <div
            key={ticker}
            className="flex items-center justify-between rounded-lg border border-border bg-card p-4 transition-colors hover:border-primary/30"
          >
            <div>
              <div className="text-sm font-medium">{name}</div>
              {data ? (
                <div className="mt-0.5 flex items-center gap-2">
                  <span className="font-mono text-xs">{data.price.toLocaleString()}</span>
                  <span className={cn("text-[10px] font-semibold", data.change_pct >= 0 ? "text-gain" : "text-loss")}>
                    {data.change_pct >= 0 ? "+" : ""}{data.change_pct.toFixed(2)}%
                  </span>
                </div>
              ) : (
                <div className="mt-0.5 text-xs text-muted-foreground">—</div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
