"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

interface CorrelationHeatmapProps {
  tickers: string[];
  matrix: number[][];
  className?: string;
}

/** Map correlation value to a Tailwind-compatible color. */
function correlationColor(value: number, isDiagonal: boolean): string {
  if (isDiagonal) return "bg-muted/50";
  const abs = Math.abs(value);
  if (abs > 0.7) return "bg-loss/60";
  if (abs > 0.3) return "bg-warning/50";
  return "bg-gain/40";
}

function correlationTextColor(value: number, isDiagonal: boolean): string {
  if (isDiagonal) return "text-subtle";
  const abs = Math.abs(value);
  if (abs > 0.7) return "text-loss";
  if (abs > 0.3) return "text-warning";
  return "text-gain";
}

export function CorrelationHeatmap({
  tickers,
  matrix,
  className,
}: CorrelationHeatmapProps) {
  const [hoveredCell, setHoveredCell] = useState<{
    row: number;
    col: number;
  } | null>(null);
  const n = tickers.length;

  return (
    <div className={cn("overflow-x-auto", className)}>
      <div
        className="inline-grid gap-px"
        style={{
          gridTemplateColumns: `auto repeat(${n}, minmax(48px, 1fr))`,
          gridTemplateRows: `auto repeat(${n}, 48px)`,
        }}
      >
        {/* Empty top-left corner */}
        <div />

        {/* Column headers */}
        {tickers.map((ticker) => (
          <div
            key={`col-${ticker}`}
            className="flex items-end justify-center pb-1"
          >
            <span className="text-[10px] font-mono text-subtle -rotate-45 origin-bottom-left whitespace-nowrap">
              {ticker}
            </span>
          </div>
        ))}

        {/* Rows */}
        {matrix.map((row, i) => (
          <>
            {/* Row header */}
            <div
              key={`row-${tickers[i]}`}
              className="flex items-center justify-end pr-2"
            >
              <span className="text-[10px] font-mono text-subtle">
                {tickers[i]}
              </span>
            </div>

            {/* Cells */}
            {row.map((value, j) => {
              const isDiagonal = i === j;
              const isHovered =
                hoveredCell?.row === i && hoveredCell?.col === j;
              return (
                <div
                  key={`${i}-${j}`}
                  className={cn(
                    "flex items-center justify-center rounded-sm transition-all cursor-default",
                    correlationColor(value, isDiagonal),
                    isHovered && "ring-1 ring-foreground/30"
                  )}
                  onMouseEnter={() => setHoveredCell({ row: i, col: j })}
                  onMouseLeave={() => setHoveredCell(null)}
                  title={
                    isDiagonal
                      ? tickers[i]
                      : `${tickers[i]} ↔ ${tickers[j]}: ${value.toFixed(2)}`
                  }
                >
                  <span
                    className={cn(
                      "text-[10px] font-mono tabular-nums font-medium",
                      correlationTextColor(value, isDiagonal)
                    )}
                  >
                    {isDiagonal ? "1.0" : value.toFixed(2)}
                  </span>
                </div>
              );
            })}
          </>
        ))}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-3 mt-3 text-[10px] text-subtle">
        <div className="flex items-center gap-1">
          <div className="size-3 rounded-sm bg-gain/40" />
          <span>Low (&lt;0.3)</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="size-3 rounded-sm bg-warning/50" />
          <span>Moderate (0.3-0.7)</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="size-3 rounded-sm bg-loss/60" />
          <span>High (&gt;0.7)</span>
        </div>
      </div>
    </div>
  );
}
