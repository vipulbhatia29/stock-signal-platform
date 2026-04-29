"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { SectionHeading } from "@/components/section-heading";
import { ScoreBadge } from "@/components/score-badge";
import { ChangeIndicator } from "@/components/change-indicator";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { useWatchlist, usePositions, useBulkSignalsByTickers } from "@/hooks/use-stocks";
import { useQueries } from "@tanstack/react-query";
import { get } from "@/lib/api";
import { cn } from "@/lib/utils";
import { formatCurrency, formatPercent } from "@/lib/format";
import type { BulkSignalItem, ForecastResponse } from "@/types/api";

type Tab = "watchlist" | "portfolio";

/** Compute period return from price_history array (chronological: oldest first). */
function periodReturn(history: number[] | null, daysBack: number): number | null {
  if (!history || history.length < 2) return null;
  const endIdx = history.length - 1;
  const startIdx = Math.max(0, endIdx - daysBack);
  const start = history[startIdx];
  const end = history[endIdx];
  if (!start || start === 0) return null;
  return ((end - start) / start) * 100;
}

/** Dense tabular view of all watchlist/portfolio metrics — the data bulletin. */
export function BulletinZone() {
  const [tab, setTab] = useState<Tab>("watchlist");
  const { data: watchlist, isLoading: wlLoading } = useWatchlist();
  const { data: positions, isLoading: posLoading } = usePositions();

  // All tickers for bulk data fetch
  const allTickers = useMemo(() => {
    const tickers = new Set<string>();
    watchlist?.forEach((w) => tickers.add(w.ticker));
    positions?.forEach((p) => tickers.add(p.ticker));
    return [...tickers];
  }, [watchlist, positions]);

  // Bulk signals (RSI, MACD, Sharpe, annual return, price_history)
  const { data: bulkSignals } = useBulkSignalsByTickers(allTickers, allTickers.length > 0);
  const signalMap = useMemo(() => {
    const m = new Map<string, BulkSignalItem>();
    bulkSignals?.items.forEach((s) => m.set(s.ticker, s));
    return m;
  }, [bulkSignals]);

  // Per-ticker forecasts (parallel queries)
  const forecastQueries = useQueries({
    queries: allTickers.map((ticker) => ({
      queryKey: ["forecast", ticker],
      queryFn: () => get<ForecastResponse>(`/forecasts/${ticker}`),
      staleTime: 5 * 60 * 1000,
      enabled: allTickers.length > 0,
    })),
  });
  const forecastMap = useMemo(() => {
    const m = new Map<string, ForecastResponse>();
    forecastQueries.forEach((q, i) => {
      if (q.data) m.set(allTickers[i], q.data);
    });
    return m;
  }, [forecastQueries, allTickers]);

  const isLoading = tab === "watchlist" ? wlLoading : posLoading;

  return (
    <section aria-label="Data Bulletin">
      <div className="flex items-center justify-between mb-3">
        <SectionHeading>Data Bulletin</SectionHeading>
        <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)}>
          <TabsList className="h-7">
            <TabsTrigger value="watchlist" className="h-6 text-[10px] px-3">
              Watchlist ({watchlist?.length ?? 0})
            </TabsTrigger>
            <TabsTrigger value="portfolio" className="h-6 text-[10px] px-3">
              Portfolio ({positions?.length ?? 0})
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full rounded-lg bg-card2" />
          ))}
        </div>
      ) : tab === "watchlist" ? (
        <WatchlistTable items={watchlist ?? []} positions={positions ?? []} signalMap={signalMap} forecastMap={forecastMap} />
      ) : (
        <PortfolioTable items={positions ?? []} watchlist={watchlist ?? []} signalMap={signalMap} forecastMap={forecastMap} />
      )}
    </section>
  );
}

// ── Column header helper ──────────────────────────────────────────────────────

function TH({ children, className, title }: { children: React.ReactNode; className?: string; title?: string }) {
  return <TableHead className={cn("text-[9px] uppercase tracking-wider whitespace-nowrap", className)} title={title}>{children}</TableHead>;
}

// ── Watchlist Table ───────────────────────────────────────────────────────────

function WatchlistTable({
  items,
  positions,
  signalMap,
  forecastMap,
}: {
  items: { ticker: string; name: string | null; current_price: number | null; change_pct: number | null; composite_score: number | null; recommendation: string | null }[];
  positions: { ticker: string }[];
  signalMap: Map<string, BulkSignalItem>;
  forecastMap: Map<string, ForecastResponse>;
}) {
  const heldTickers = useMemo(() => new Set(positions.map((p) => p.ticker)), [positions]);

  if (!items.length) {
    return <p className="text-sm text-muted-foreground py-4">No stocks in watchlist</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <Table>
        <TableHeader className="bg-card2">
          <TableRow>
            <TH>Ticker</TH>
            <TH className="text-right">Price</TH>
            <TH className="text-right">1D</TH>
            <TH className="text-right">1W</TH>
            <TH className="text-right">30D</TH>
            <TH className="text-right">Ann. Ret</TH>
            <TH className="text-center">Score</TH>
            <TH className="text-right">RSI</TH>
            <TH>MACD</TH>
            <TH>SMA</TH>
            <TH className="text-right">Sharpe</TH>
            <TH className="text-right">Vol</TH>
            <TH className="text-right" title="Expected return over the next 90 days based on signal analysis">90D Outlook</TH>
            <TH className="text-center">Action</TH>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item) => {
            const sig = signalMap.get(item.ticker);
            const fc = forecastMap.get(item.ticker);
            const fc90 = fc?.horizons?.find((h) => h.horizon_days === 90);
            const chg1w = periodReturn(sig?.price_history ?? null, 5);
            const chg30d = periodReturn(sig?.price_history ?? null, 30);

            return (
              <TableRow key={item.ticker} className="hover:bg-hov">
                <TableCell className="py-1.5">
                  <div className="flex items-center gap-1.5">
                    <Link href={`/stocks/${item.ticker}`} className="font-mono text-xs font-bold hover:underline">
                      {item.ticker}
                    </Link>
                    {heldTickers.has(item.ticker) && (
                      <span className="rounded bg-primary/10 px-1 py-0.5 text-[7px] font-semibold text-primary">Held</span>
                    )}
                  </div>
                  <div className="text-[9px] text-muted-foreground truncate max-w-[100px]">{item.name}</div>
                </TableCell>
                <TableCell className="py-1.5 text-right font-mono text-xs">
                  {item.current_price != null ? `$${item.current_price.toFixed(2)}` : "—"}
                </TableCell>
                <Cell value={item.change_pct} />
                <Cell value={chg1w} />
                <Cell value={chg30d} />
                <Cell value={sig?.annual_return != null ? sig.annual_return * 100 : null} />
                <TableCell className="py-1.5 text-center">
                  <ScoreBadge score={item.composite_score} size="xs" />
                </TableCell>
                <TableCell className="py-1.5 text-right font-mono text-xs">
                  {sig?.rsi_value != null ? Math.round(sig.rsi_value) : "—"}
                </TableCell>
                <TableCell className="py-1.5 text-xs">
                  <MacdLabel signal={sig?.macd_signal ?? null} />
                </TableCell>
                <TableCell className="py-1.5 text-xs">
                  <SmaLabel signal={sig?.sma_signal ?? null} />
                </TableCell>
                <TableCell className="py-1.5 text-right font-mono text-xs">
                  {sig?.sharpe_ratio != null ? sig.sharpe_ratio.toFixed(2) : "—"}
                </TableCell>
                <TableCell className="py-1.5 text-right font-mono text-xs">
                  {sig?.volatility != null ? `${(sig.volatility * 100).toFixed(1)}%` : "—"}
                </TableCell>
                <TableCell className="py-1.5 text-right font-mono text-xs">
                  {fc90 ? (
                    <span className={cn(
                      fc90.expected_return_pct > 0 && "text-gain",
                      fc90.expected_return_pct < 0 && "text-loss",
                      !(fc90.expected_return_pct > 0) && !(fc90.expected_return_pct < 0) && "text-muted-foreground",
                    )}>
                      {fc90.expected_return_pct > 0 ? "+" : ""}
                      {fc90.expected_return_pct.toFixed(1)}%
                    </span>
                  ) : "—"}
                </TableCell>
                <TableCell className="py-1.5 text-center">
                  {item.recommendation ? <ActionBadge action={item.recommendation} /> : "—"}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

// ── Portfolio Table ───────────────────────────────────────────────────────────

function PortfolioTable({
  items,
  watchlist,
  signalMap,
  forecastMap,
}: {
  items: { ticker: string; shares: number; avg_cost_basis: number; current_price: number | null; market_value: number | null; unrealized_pnl: number | null; unrealized_pnl_pct: number | null; allocation_pct: number | null }[];
  watchlist: { ticker: string; change_pct: number | null; composite_score: number | null; recommendation: string | null }[];
  signalMap: Map<string, BulkSignalItem>;
  forecastMap: Map<string, ForecastResponse>;
}) {
  const watchMap = useMemo(() => new Map(watchlist.map((w) => [w.ticker, w])), [watchlist]);

  if (!items.length) {
    return <p className="text-sm text-muted-foreground py-4">No positions — log a transaction to start</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <Table>
        <TableHeader className="bg-card2">
          <TableRow>
            <TH>Ticker</TH>
            <TH className="text-right">Shares</TH>
            <TH className="text-right">Avg Cost</TH>
            <TH className="text-right">Price</TH>
            <TH className="text-right">1D</TH>
            <TH className="text-right">1W</TH>
            <TH className="text-right">30D</TH>
            <TH className="text-right">Mkt Val</TH>
            <TH className="text-right">P&L</TH>
            <TH className="text-right">P&L %</TH>
            <TH className="text-center">Score</TH>
            <TH className="text-right" title="Expected return over the next 90 days based on signal analysis">90D Outlook</TH>
            <TH className="text-center">Action</TH>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((pos) => {
            const w = watchMap.get(pos.ticker);
            const sig = signalMap.get(pos.ticker);
            const fc = forecastMap.get(pos.ticker);
            const fc90 = fc?.horizons?.find((h) => h.horizon_days === 90);
            const chg1w = periodReturn(sig?.price_history ?? null, 5);
            const chg30d = periodReturn(sig?.price_history ?? null, 30);

            return (
              <TableRow key={pos.ticker} className="hover:bg-hov">
                <TableCell className="py-1.5">
                  <Link href={`/stocks/${pos.ticker}`} className="font-mono text-xs font-bold hover:underline">
                    {pos.ticker}
                  </Link>
                </TableCell>
                <TableCell className="py-1.5 text-right font-mono text-xs">{pos.shares}</TableCell>
                <TableCell className="py-1.5 text-right font-mono text-xs">{formatCurrency(pos.avg_cost_basis)}</TableCell>
                <TableCell className="py-1.5 text-right font-mono text-xs">
                  {pos.current_price != null ? formatCurrency(pos.current_price) : "—"}
                </TableCell>
                <Cell value={w?.change_pct ?? null} />
                <Cell value={chg1w} />
                <Cell value={chg30d} />
                <TableCell className="py-1.5 text-right font-mono text-xs">
                  {pos.market_value != null ? formatCurrency(pos.market_value) : "—"}
                </TableCell>
                <TableCell className="py-1.5 text-right">
                  {pos.unrealized_pnl != null ? (
                    <span className={cn("font-mono text-xs", pos.unrealized_pnl >= 0 ? "text-gain" : "text-loss")}>
                      {pos.unrealized_pnl >= 0 ? "+" : ""}{formatCurrency(pos.unrealized_pnl)}
                    </span>
                  ) : "—"}
                </TableCell>
                <Cell value={pos.unrealized_pnl_pct} />
                <TableCell className="py-1.5 text-center">
                  <ScoreBadge score={w?.composite_score ?? null} size="xs" />
                </TableCell>
                <TableCell className="py-1.5 text-right font-mono text-xs">
                  {fc90 ? (
                    <span className={cn(
                      fc90.expected_return_pct > 0 && "text-gain",
                      fc90.expected_return_pct < 0 && "text-loss",
                      !(fc90.expected_return_pct > 0) && !(fc90.expected_return_pct < 0) && "text-muted-foreground",
                    )}>
                      {fc90.expected_return_pct > 0 ? "+" : ""}
                      {fc90.expected_return_pct.toFixed(1)}%
                    </span>
                  ) : "—"}
                </TableCell>
                <TableCell className="py-1.5 text-center">
                  {w?.recommendation ? <ActionBadge action={w.recommendation} /> : "—"}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

// ── Shared sub-components ─────────────────────────────────────────────────────

function Cell({ value }: { value: number | null | undefined }) {
  if (value == null) return <TableCell className="py-1.5 text-right font-mono text-xs text-muted-foreground">—</TableCell>;
  const color = value > 0 ? "text-gain" : value < 0 ? "text-loss" : "text-muted-foreground";
  return (
    <TableCell className={cn("py-1.5 text-right font-mono text-xs", color)}>
      {value > 0 ? "+" : ""}{value.toFixed(2)}%
    </TableCell>
  );
}

function MacdLabel({ signal }: { signal: string | null }) {
  if (!signal) return <span className="text-muted-foreground">—</span>;
  const bull = signal.includes("bullish");
  const bear = signal.includes("bearish");
  return (
    <span className={cn("text-[10px]", bull ? "text-gain" : bear ? "text-loss" : "text-muted-foreground")}>
      {bull ? "▲ Bull" : bear ? "▼ Bear" : signal}
    </span>
  );
}

function SmaLabel({ signal }: { signal: string | null }) {
  if (!signal) return <span className="text-muted-foreground">—</span>;
  const positive = signal === "golden_cross" || signal === "above";
  const negative = signal === "death_cross" || signal === "below";
  return (
    <span className={cn("text-[10px]", positive ? "text-gain" : negative ? "text-loss" : "text-muted-foreground")}>
      {signal === "golden_cross" ? "Golden" : signal === "death_cross" ? "Death" : signal === "above" ? "Above" : signal === "below" ? "Below" : signal}
    </span>
  );
}

function ActionBadge({ action }: { action: string }) {
  const colors: Record<string, string> = {
    BUY: "bg-gain/15 text-gain",
    WATCH: "bg-warning/15 text-warning",
    AVOID: "bg-loss/15 text-loss",
  };
  return (
    <span className={cn("inline-flex rounded-full px-2 py-0.5 text-[9px] font-semibold", colors[action] ?? "bg-muted text-muted-foreground")}>
      {action}
    </span>
  );
}
