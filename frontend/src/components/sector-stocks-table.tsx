"use client";

import { cn } from "@/lib/utils";
import { ScoreBar } from "@/components/score-bar";
import { ChangeIndicator } from "@/components/change-indicator";
import { formatCurrency } from "@/lib/format";
import type { SectorStock } from "@/types/api";

interface SectorStocksTableProps {
  stocks: SectorStock[];
  onTickerClick?: (ticker: string) => void;
  className?: string;
}

export function SectorStocksTable({
  stocks,
  onTickerClick,
  className,
}: SectorStocksTableProps) {
  const userStocks = stocks.filter((s) => s.is_held || s.is_watched);
  const otherStocks = stocks.filter((s) => !s.is_held && !s.is_watched);

  return (
    <div className={cn("space-y-3", className)}>
      {userStocks.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-subtle uppercase tracking-wider mb-2">
            Your Stocks
          </h4>
          <StockRows stocks={userStocks} onTickerClick={onTickerClick} highlight />
        </div>
      )}

      {otherStocks.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-subtle uppercase tracking-wider mb-2">
            Top Sector Stocks
          </h4>
          <StockRows stocks={otherStocks} onTickerClick={onTickerClick} />
        </div>
      )}
    </div>
  );
}

function StockRows({
  stocks,
  onTickerClick,
  highlight = false,
}: {
  stocks: SectorStock[];
  onTickerClick?: (ticker: string) => void;
  highlight?: boolean;
}) {
  return (
    <div className="rounded-md border border-border overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/30">
            <th className="px-3 py-2 text-left text-xs font-medium text-subtle">Ticker</th>
            <th className="px-3 py-2 text-left text-xs font-medium text-subtle">Name</th>
            <th className="px-3 py-2 text-left text-xs font-medium text-subtle w-24">Score</th>
            <th className="px-3 py-2 text-right text-xs font-medium text-subtle">Price</th>
            <th className="px-3 py-2 text-right text-xs font-medium text-subtle">Return</th>
            <th className="px-3 py-2 text-center text-xs font-medium text-subtle w-16">Status</th>
          </tr>
        </thead>
        <tbody>
          {stocks.map((stock) => (
            <tr
              key={stock.ticker}
              onClick={() => onTickerClick?.(stock.ticker)}
              className={cn(
                "border-b border-border last:border-0 transition-colors",
                highlight && "bg-primary/5",
                onTickerClick && "cursor-pointer hover:bg-muted/30"
              )}
            >
              <td className="px-3 py-2 font-mono font-medium text-foreground">
                {stock.ticker}
              </td>
              <td className="px-3 py-2 text-subtle truncate max-w-[180px]">
                {stock.name}
              </td>
              <td className="px-3 py-2">
                {stock.composite_score !== null ? (
                  <div className="flex items-center gap-2">
                    <ScoreBar score={stock.composite_score} className="w-12" />
                    <span className="text-xs font-mono tabular-nums">
                      {stock.composite_score.toFixed(1)}
                    </span>
                  </div>
                ) : (
                  <span className="text-subtle">—</span>
                )}
              </td>
              <td className="px-3 py-2 text-right font-mono tabular-nums">
                {stock.current_price !== null
                  ? formatCurrency(stock.current_price)
                  : "—"}
              </td>
              <td className="px-3 py-2 text-right">
                <ChangeIndicator value={stock.return_pct} size="sm" showIcon={false} />
              </td>
              <td className="px-3 py-2 text-center">
                {stock.is_held ? (
                  <span className="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                    Held
                  </span>
                ) : stock.is_watched ? (
                  <span className="inline-flex items-center rounded-full bg-warning/10 px-2 py-0.5 text-xs font-medium text-warning">
                    Watched
                  </span>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
