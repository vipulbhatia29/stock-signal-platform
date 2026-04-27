"use client";

import { useMemo } from "react";
import { ArrowUpRight, ArrowDownRight, Eye, Briefcase } from "lucide-react";
import Link from "next/link";
import { SectionHeading } from "@/components/section-heading";
import { SectorPerformanceBars } from "@/components/sector-performance-bars";
import { EmptyState } from "@/components/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { ScoreBadge } from "@/components/score-badge";
import { useWatchlist, useMarketBriefing, usePositions } from "@/hooks/use-stocks";
import { cn } from "@/lib/utils";
import type { WatchlistItem } from "@/types/api";

const ACTION_STYLES = {
  BUY: { icon: ArrowUpRight, bg: "bg-gain/10", text: "text-gain", border: "border-gain/20" },
  WATCH: { icon: Eye, bg: "bg-cyan/10", text: "text-cyan", border: "border-cyan/20" },
  AVOID: { icon: ArrowDownRight, bg: "bg-loss/10", text: "text-loss", border: "border-loss/20" },
} as const;

function buildReasoning(item: WatchlistItem): string {
  const factors: string[] = [];
  if (item.macd_signal_label) {
    const label = item.macd_signal_label.includes("bullish") ? "Bullish MACD" : item.macd_signal_label.includes("bearish") ? "Bearish MACD" : `MACD ${item.macd_signal_label}`;
    factors.push(label);
  }
  if (item.rsi_value != null) {
    const rsi = Math.round(item.rsi_value);
    if (rsi < 30) factors.push(`RSI oversold (${rsi})`);
    else if (rsi > 70) factors.push(`RSI overbought (${rsi})`);
    else factors.push(`stable RSI (${rsi})`);
  }
  if (item.change_pct != null) {
    if (Math.abs(item.change_pct) > 3) factors.push(`${item.change_pct > 0 ? "+" : ""}${item.change_pct.toFixed(1)}% today`);
  }
  if (factors.length === 0) return "Awaiting signal data";
  return factors.slice(0, 3).join(". ") + ".";
}

function getConfidence(score: number | null): string {
  if (score == null) return "";
  if (score >= 8) return "HIGH";
  if (score >= 5) return "MEDIUM";
  return "LOW";
}

/** Action Required — sorted by score, shows reasoning + recommendation + sector donut. */
export function ActionRequiredZone() {
  const { data: watchlist, isLoading } = useWatchlist();
  const { data: briefing } = useMarketBriefing();
  const { data: positions } = usePositions();

  const heldTickers = useMemo(() => new Set(positions?.map((p) => p.ticker) ?? []), [positions]);

  const actionItems = useMemo(() => {
    if (!watchlist) return [];
    return watchlist
      .filter((w) => w.composite_score != null)
      .sort((a, b) => (b.composite_score ?? 0) - (a.composite_score ?? 0));
  }, [watchlist]);

  const sectorBars = useMemo(() => {
    if (!briefing?.sector_performance?.length) return [];
    return briefing.sector_performance.map((s) => ({
      sector: s.sector,
      changePct: s.change_pct,
    }));
  }, [briefing]);

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      {/* Action Required list */}
      <section className="lg:col-span-2" aria-label="Action Required">
        <SectionHeading>Action Required</SectionHeading>

        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full rounded-lg bg-card2" />
            ))}
          </div>
        ) : actionItems.length === 0 ? (
          <EmptyState icon={Eye} title="No actions" description="Add stocks to your watchlist to get recommendations" />
        ) : (
          <div className="space-y-2">
            {actionItems.map((item) => {
              const action = (item.recommendation ?? "WATCH") as keyof typeof ACTION_STYLES;
              const s = ACTION_STYLES[action] ?? ACTION_STYLES.WATCH;
              const Icon = s.icon;

              return (
                <Link
                  key={item.ticker}
                  href={`/stocks/${item.ticker}`}
                  className="flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-3 transition-colors hover:border-primary/30 hover:bg-hov"
                >
                  <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-lg", s.bg)}>
                    <Icon className={cn("h-4 w-4", s.text)} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-bold">{item.ticker}</span>
                      {heldTickers.has(item.ticker) && (
                        <span className="flex items-center gap-0.5 rounded bg-primary/10 px-1 py-0.5 text-[8px] font-semibold text-primary">
                          <Briefcase className="h-2.5 w-2.5" /> Held
                        </span>
                      )}
                      <span className={cn("rounded border px-1.5 py-0.5 text-[9px] font-semibold", s.bg, s.text, s.border)}>
                        {action}
                      </span>
                      <span className="text-[9px] text-muted-foreground">{getConfidence(item.composite_score)}</span>
                    </div>
                    <p className="mt-0.5 truncate text-[10px] text-muted-foreground">
                      {buildReasoning(item)}
                    </p>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <ScoreBadge score={item.composite_score} size="sm" />
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </section>

      {/* Sector Performance — today's market context */}
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
