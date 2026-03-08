"use client";

import Link from "next/link";
import { ChevronUpIcon, ChevronDownIcon } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { ScoreBadge } from "@/components/score-badge";
import { SignalBadge } from "@/components/signal-badge";
import { formatNumber, formatPercent } from "@/lib/format";
import { scoreToSentiment, SENTIMENT_BG_CLASSES } from "@/lib/signals";
import { cn } from "@/lib/utils";
import type { BulkSignalItem } from "@/types/api";

interface ScreenerTableProps {
  items: BulkSignalItem[];
  sortBy: string;
  sortOrder: "asc" | "desc";
  onSort: (column: string) => void;
  isLoading: boolean;
}

const COLUMNS = [
  { key: "ticker", label: "Ticker", sortable: true },
  { key: "name", label: "Name", sortable: false },
  { key: "sector", label: "Sector", sortable: false },
  { key: "rsi_value", label: "RSI", sortable: true },
  { key: "macd_signal", label: "MACD", sortable: false },
  { key: "sma_signal", label: "SMA", sortable: false },
  { key: "annual_return", label: "Return", sortable: true },
  { key: "sharpe_ratio", label: "Sharpe", sortable: true },
  { key: "composite_score", label: "Score", sortable: true },
];

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

export function ScreenerTable({
  items,
  sortBy,
  sortOrder,
  onSort,
  isLoading,
}: ScreenerTableProps) {
  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            {COLUMNS.map((col) => (
              <TableHead
                key={col.key}
                className={cn(
                  col.sortable && "cursor-pointer select-none hover:text-foreground"
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
          {items.map((item) => {
            const sentiment = scoreToSentiment(item.composite_score);
            const rowBg =
              sentiment === "neutral" ? "" : SENTIMENT_BG_CLASSES[sentiment];

            return (
              <TableRow key={item.ticker} className={rowBg}>
                <TableCell className="font-mono font-semibold">
                  <Link
                    href={`/stocks/${item.ticker}`}
                    className="hover:underline"
                  >
                    {item.ticker}
                  </Link>
                </TableCell>
                <TableCell className="max-w-[200px] truncate">
                  {item.name}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {item.sector || "—"}
                </TableCell>
                <TableCell className="tabular-nums">
                  {formatNumber(item.rsi_value, 1)}
                  {item.rsi_signal && (
                    <span className="ml-1">
                      <SignalBadge signal={item.rsi_signal} type="rsi" />
                    </span>
                  )}
                </TableCell>
                <TableCell>
                  <SignalBadge signal={item.macd_signal} type="macd" />
                </TableCell>
                <TableCell>
                  <SignalBadge signal={item.sma_signal} type="sma" />
                </TableCell>
                <TableCell className="tabular-nums">
                  {formatPercent(item.annual_return)}
                </TableCell>
                <TableCell className="tabular-nums">
                  {formatNumber(item.sharpe_ratio)}
                </TableCell>
                <TableCell>
                  <ScoreBadge score={item.composite_score} size="sm" />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
