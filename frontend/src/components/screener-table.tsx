"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronUpIcon, ChevronDownIcon } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { Briefcase } from "lucide-react";
import { ChangeIndicator } from "@/components/change-indicator";
import { ScoreBadge } from "@/components/score-badge";
import { ScoreBar } from "@/components/score-bar";
import { SignalBadge } from "@/components/signal-badge";
import { SignalMeter } from "@/components/signal-meter";
import { formatNumber, formatPercent } from "@/lib/format";
import { scoreToSentiment, SENTIMENT_BG_CLASSES } from "@/lib/signals";
import { useDensity } from "@/lib/density-context";
import { cn } from "@/lib/utils";
import type { BulkSignalItem } from "@/types/api";

// ── Column definitions ────────────────────────────────────────────────────────

interface Column {
  key: string;
  label: string;
  sortable: boolean;
  render: (item: BulkSignalItem, heldTickers?: Set<string>) => React.ReactNode;
}

const COL: Record<string, Column> = {
  ticker: {
    key: "ticker",
    label: "Ticker",
    sortable: true,
    render: (item, heldSet) => (
      <div className="flex items-center gap-1.5">
        <Link
          href={`/stocks/${item.ticker}`}
          className="font-mono font-semibold hover:underline"
          onClick={(e) => e.stopPropagation()}
        >
          {item.ticker}
        </Link>
        {heldSet?.has(item.ticker) && (
          <span className="flex items-center gap-0.5 rounded bg-[var(--cdim)] px-1 py-0.5 text-[8px] font-semibold text-cyan">
            <Briefcase className="h-2.5 w-2.5" />
          </span>
        )}
      </div>
    ),
  },
  name: {
    key: "name",
    label: "Name",
    sortable: false,
    render: (item) => (
      <span className="max-w-[180px] truncate block">{item.name}</span>
    ),
  },
  sector: {
    key: "sector",
    label: "Sector",
    sortable: false,
    render: (item) => (
      <span className="text-muted-foreground">{item.sector || "—"}</span>
    ),
  },
  rsi: {
    key: "rsi_value",
    label: "RSI",
    sortable: true,
    render: (item) => (
      <span className="tabular-nums">
        {formatNumber(item.rsi_value, 1)}
        {item.rsi_signal && (
          <span className="ml-1">
            <SignalBadge signal={item.rsi_signal} type="rsi" />
          </span>
        )}
      </span>
    ),
  },
  macd: {
    key: "macd_signal",
    label: "MACD",
    sortable: false,
    render: (item) => <SignalBadge signal={item.macd_signal} type="macd" />,
  },
  sma: {
    key: "sma_signal",
    label: "SMA",
    sortable: false,
    render: (item) => <SignalBadge signal={item.sma_signal} type="sma" />,
  },
  bb: {
    key: "bb_position",
    label: "Bollinger",
    sortable: false,
    render: (item) => (
      <span className="text-muted-foreground text-sm">{item.bb_position || "—"}</span>
    ),
  },
  score: {
    key: "composite_score",
    label: "Score",
    sortable: true,
    render: (item) => (
      <div className="flex items-center gap-2">
        <ScoreBar score={item.composite_score ?? 0} className="w-20" />
        <ScoreBadge score={item.composite_score} size="xs" />
      </div>
    ),
  },
  meter: {
    key: "composite_score_meter",
    label: "Signal Strength",
    sortable: false,
    render: (item) => (
      <div className="w-24">
        <SignalMeter score={item.composite_score} size="sm" />
      </div>
    ),
  },
  annualReturn: {
    key: "annual_return",
    label: "Annual Return",
    sortable: true,
    render: (item) => (
      <ChangeIndicator value={item.annual_return} format="percent" size="sm" />
    ),
  },
  volatility: {
    key: "volatility",
    label: "Volatility",
    sortable: true,
    render: (item) => (
      <span className="tabular-nums">{formatPercent(item.volatility)}</span>
    ),
  },
  sharpe: {
    key: "sharpe_ratio",
    label: "Sharpe",
    sortable: true,
    render: (item) => (
      <span className="tabular-nums">{formatNumber(item.sharpe_ratio)}</span>
    ),
  },
};

// ── Tab presets ───────────────────────────────────────────────────────────────

type TabKey = "overview" | "signals" | "performance";

const TAB_COLUMNS: Record<TabKey, string[]> = {
  overview: ["ticker", "name", "sector", "score"],
  signals: ["ticker", "rsi", "macd", "sma", "bb", "score", "meter"],
  performance: ["ticker", "annualReturn", "volatility", "sharpe", "score"],
};

const TABS: { key: TabKey; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "signals", label: "Signals" },
  { key: "performance", label: "Performance" },
];

// ── Props ─────────────────────────────────────────────────────────────────────

interface ScreenerTableProps {
  items: BulkSignalItem[];
  sortBy: string;
  sortOrder: "asc" | "desc";
  onSort: (column: string) => void;
  isLoading: boolean;
  activeTab: TabKey;
  onTabChange: (tab: TabKey) => void;
  heldTickers?: Set<string>;
}

function SortIcon({
  column,
  sortBy,
  sortOrder,
}: {
  column: string;
  sortBy: string;
  sortOrder: "asc" | "desc";
}) {
  if (column !== sortBy) return null;
  return sortOrder === "asc" ? (
    <ChevronUpIcon className="ml-1 inline size-3.5" />
  ) : (
    <ChevronDownIcon className="ml-1 inline size-3.5" />
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

export function ScreenerTable({
  items,
  sortBy,
  sortOrder,
  onSort,
  isLoading,
  activeTab,
  onTabChange,
  heldTickers,
}: ScreenerTableProps) {
  const router = useRouter();
  const { density } = useDensity();

  const columns = TAB_COLUMNS[activeTab].map((k) => COL[k]);
  const rowPadding = density === "compact" ? "py-1.5" : "py-3";
  const textSize = density === "compact" ? "text-xs" : "text-sm";

  return (
    <div className="space-y-2">
      <Tabs value={activeTab} onValueChange={(v) => onTabChange(v as TabKey)}>
        <TabsList className="h-8">
          {TABS.map((t) => (
            <TabsTrigger key={t.key} value={t.key} className="h-7 text-xs">
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <Table>
            <TableHeader className="sticky top-0 z-10 bg-card2">
              <TableRow>
                {columns.map((col) => (
                  <TableHead
                    key={col.key}
                    className={cn(
                      "text-subtle uppercase text-[9.5px] tracking-[0.1em]",
                      col.sortable &&
                        "cursor-pointer select-none hover:text-foreground",
                      col.key === sortBy && "text-foreground"
                    )}
                    onClick={() => col.sortable && onSort(col.key)}
                  >
                    {col.label}
                    {col.sortable && (
                      <SortIcon
                        column={col.key}
                        sortBy={sortBy}
                        sortOrder={sortOrder}
                      />
                    )}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item, i) => {
                const sentiment = scoreToSentiment(item.composite_score);
                const rowBg =
                  sentiment === "neutral" ? "" : SENTIMENT_BG_CLASSES[sentiment];

                return (
                  <TableRow
                    key={item.ticker}
                    className={cn(
                      rowBg,
                      "cursor-pointer hover:bg-hov",
                      i < 12 && "animate-fade-slide-up",
                    )}
                    style={
                      i < 12
                        ? ({ '--stagger-delay': `${i * 30}ms` } as React.CSSProperties)
                        : undefined
                    }
                    onClick={() => router.push(`/stocks/${item.ticker}`)}
                  >
                    {columns.map((col) => (
                      <TableCell
                        key={col.key}
                        className={cn(rowPadding, textSize)}
                      >
                        {col.render(item, heldTickers)}
                      </TableCell>
                    ))}
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}

export type { TabKey };
