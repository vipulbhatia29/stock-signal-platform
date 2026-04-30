"use client";

import { useMemo, useState } from "react";
import { ArrowUpRight, ArrowDownRight, Eye, Briefcase, ChevronDown, ChevronUp, AlertTriangle } from "lucide-react";
import Link from "next/link";
import { SectionHeading } from "@/components/section-heading";
import { SectorPerformanceBars } from "@/components/sector-performance-bars";
import { Skeleton } from "@/components/ui/skeleton";
import { ScoreBadge } from "@/components/score-badge";
import { useWatchlist, useMarketBriefing, usePositions } from "@/hooks/use-stocks";
import { cn } from "@/lib/utils";
import type { WatchlistItem } from "@/types/api";

// ── Types & constants ────────────────────────────────────────────────────────

type SellReason = "held_big_drop" | "held_weak" | "held_overbought";
type BuyReason = "buy_signal";
type ActionReason = SellReason | BuyReason;

interface ActionItem {
  item: WatchlistItem;
  reason: ActionReason;
  sortPriority: number;
}

const VISIBLE_COUNT = 4;

// ── Helpers ──────────────────────────────────────────────────────────────────

function sellReasonText(item: WatchlistItem, reason: SellReason): string {
  const score = item.composite_score ?? 0;
  switch (reason) {
    case "held_big_drop":
      return `${item.change_pct!.toFixed(1)}% drop today. Review thesis.`;
    case "held_weak":
      return `Weak signals (${score}/10). Consider exiting.`;
    case "held_overbought":
      return `RSI ${Math.round(item.rsi_value!)} — take-profit window.`;
  }
}

function buyReasonText(item: WatchlistItem): string {
  return `Score ${item.composite_score}/10. Multiple technicals bullish.`;
}

function urgencyLabel(reason: ActionReason): string {
  switch (reason) {
    case "held_big_drop":
    case "held_weak":
      return "URGENT";
    case "buy_signal":
      return "OPPORTUNITY";
    case "held_overbought":
      return "CONSIDER";
  }
}

// ── Main component ───────────────────────────────────────────────────────────

export function ActionRequiredZone() {
  const { data: watchlist, isLoading } = useWatchlist();
  const { data: briefing } = useMarketBriefing();
  const { data: positions } = usePositions();

  const heldTickers = useMemo(() => new Set(positions?.map((p) => p.ticker) ?? []), [positions]);

  const { sellItems, buyItems } = useMemo(() => {
    if (!watchlist) return { sellItems: [], buyItems: [] };
    const sell: ActionItem[] = [];
    const buy: ActionItem[] = [];

    for (const w of watchlist) {
      if (w.composite_score == null) continue;
      const isHeld = heldTickers.has(w.ticker);

      // Sell-side: only held positions
      if (isHeld && w.change_pct != null && w.change_pct < -5) {
        sell.push({ item: w, reason: "held_big_drop", sortPriority: 0 });
        continue;
      }
      if (isHeld && w.composite_score < 5) {
        sell.push({ item: w, reason: "held_weak", sortPriority: 1 });
        continue;
      }
      if (isHeld && w.rsi_value != null && w.rsi_value > 70) {
        sell.push({ item: w, reason: "held_overbought", sortPriority: 2 });
        continue;
      }

      // Buy-side: strong signals
      if (w.composite_score >= 8) {
        buy.push({ item: w, reason: "buy_signal", sortPriority: 0 });
      }
    }

    sell.sort((a, b) => a.sortPriority - b.sortPriority);
    buy.sort((a, b) => (b.item.composite_score ?? 0) - (a.item.composite_score ?? 0));
    return { sellItems: sell, buyItems: buy };
  }, [watchlist, heldTickers]);

  const sectorBars = useMemo(() => {
    if (!briefing?.sector_performance?.length) return [];
    return briefing.sector_performance.map((s) => ({
      sector: s.sector,
      changePct: s.change_pct,
    }));
  }, [briefing]);

  const hasAnyActions = sellItems.length > 0 || buyItems.length > 0;

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      {/* Action Required — split columns */}
      <section className="lg:col-span-2" aria-label="Action Required">
        <SectionHeading>Action Required</SectionHeading>

        {isLoading ? (
          <div className="grid grid-cols-2 gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full rounded-lg bg-card2" />
            ))}
          </div>
        ) : !hasAnyActions ? (
          <div className="rounded-lg border border-border bg-card p-6 text-center">
            <Eye className="mx-auto h-5 w-5 text-muted-foreground mb-2" />
            <p className="text-xs text-muted-foreground">All clear — no immediate actions needed.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <SignalColumn
              title="Sell Signals"
              titleColor="text-loss"
              items={sellItems}
              heldTickers={heldTickers}
              emptyText="No sell signals"
              renderReason={(item, reason) => sellReasonText(item, reason as SellReason)}
              side="sell"
            />
            <SignalColumn
              title="Buy Signals"
              titleColor="text-gain"
              items={buyItems}
              heldTickers={heldTickers}
              emptyText="No buy signals"
              renderReason={(item) => buyReasonText(item)}
              side="buy"
            />
          </div>
        )}
      </section>

      {/* Sector Performance */}
      <section aria-label="Sector Performance">
        <SectionHeading>Sector Performance</SectionHeading>
        {sectorBars.length > 0 ? (
          <Link href="/sectors">
            <div className="rounded-lg border border-border bg-card p-4 transition-colors hover:border-primary/30 cursor-pointer">
              <SectorPerformanceBars sectors={sectorBars} />
              <p className="text-[9px] text-muted-foreground hover:text-primary transition-colors mt-3 text-center">
                Click to explore sectors →
              </p>
            </div>
          </Link>
        ) : (
          <div className="rounded-lg border border-border bg-card p-6 text-center text-xs text-muted-foreground">
            Sector data loading…
          </div>
        )}
      </section>
    </div>
  );
}

// ── Signal column (sell or buy) ──────────────────────────────────────────────

function SignalColumn({
  title,
  titleColor,
  items,
  heldTickers,
  emptyText,
  renderReason,
  side,
}: {
  title: string;
  titleColor: string;
  items: ActionItem[];
  heldTickers: Set<string>;
  emptyText: string;
  renderReason: (item: WatchlistItem, reason: ActionReason) => string;
  side: "sell" | "buy";
}) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? items : items.slice(0, VISIBLE_COUNT);
  const hasMore = items.length > VISIBLE_COUNT;
  const Icon = side === "sell" ? ArrowDownRight : ArrowUpRight;
  const accentColor = side === "sell" ? "text-loss" : "text-gain";
  const accentBg = side === "sell" ? "bg-loss/10" : "bg-gain/10";
  const accentBorder = side === "sell" ? "border-loss/20" : "border-gain/20";

  return (
    <div>
      <div className="flex items-center gap-1.5 mb-2">
        <Icon className={cn("h-3.5 w-3.5", accentColor)} />
        <span className={cn("text-[10px] font-semibold uppercase tracking-wider", titleColor)}>
          {title}
        </span>
        <span className="text-[9px] text-muted-foreground">({items.length})</span>
      </div>

      {items.length === 0 ? (
        <div className="rounded-lg border border-border bg-card px-4 py-6 text-center text-[10px] text-muted-foreground">
          {emptyText}
        </div>
      ) : (
        <div className="space-y-1.5">
          {visible.map(({ item, reason }) => {
            const isHeld = heldTickers.has(item.ticker);
            const urgency = urgencyLabel(reason);
            const isUrgent = reason === "held_big_drop" || reason === "held_weak";

            return (
              <Link
                key={item.ticker}
                href={`/stocks/${item.ticker}`}
                className={cn(
                  "flex items-center gap-2.5 rounded-lg border bg-card px-3 py-2.5 transition-colors hover:border-primary/30 hover:bg-hov",
                  isUrgent ? "border-loss/30" : "border-border",
                )}
              >
                <div className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-md", accentBg)}>
                  {isUrgent ? (
                    <AlertTriangle className={cn("h-3.5 w-3.5", accentColor)} />
                  ) : (
                    <Icon className={cn("h-3.5 w-3.5", accentColor)} />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono text-xs font-bold">{item.ticker}</span>
                    {isHeld && (
                      <span className="flex items-center gap-0.5 rounded bg-primary/10 px-1 py-0.5 text-[7px] font-semibold text-primary">
                        <Briefcase className="h-2 w-2" /> Held
                      </span>
                    )}
                    <span className={cn(
                      "rounded px-1 py-0.5 text-[7px] font-semibold",
                      accentBg, accentColor,
                    )}>
                      {urgency}
                    </span>
                  </div>
                  <p className="mt-0.5 truncate text-[9px] text-muted-foreground">
                    {renderReason(item, reason)}
                  </p>
                </div>
                <ScoreBadge score={item.composite_score} size="xs" />
              </Link>
            );
          })}

          {hasMore && (
            <button
              onClick={() => setExpanded((prev) => !prev)}
              className={cn(
                "flex w-full items-center justify-center gap-1 rounded-lg border px-3 py-1.5 text-[9px] transition-colors hover:text-foreground",
                accentBorder, "text-muted-foreground hover:border-primary/30",
              )}
            >
              {expanded ? (
                <>
                  <ChevronUp className="h-3 w-3" />
                  Show less
                </>
              ) : (
                <>
                  <ChevronDown className="h-3 w-3" />
                  {items.length - VISIBLE_COUNT} more
                </>
              )}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
