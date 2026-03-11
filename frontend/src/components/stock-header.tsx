"use client";

import { StarIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScoreBadge } from "@/components/score-badge";
import { cn } from "@/lib/utils";

interface StockHeaderProps {
  ticker: string;
  name: string | null;
  sector: string | null;
  score: number | null;
  isInWatchlist: boolean;
  onToggleWatchlist: () => void;
}

export function StockHeader({
  ticker,
  name,
  sector,
  score,
  isInWatchlist,
  onToggleWatchlist,
}: StockHeaderProps) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <div className="flex items-center gap-3">
          <h1 className="font-mono text-2xl font-bold">{ticker}</h1>
          <ScoreBadge score={score} size="lg" />
        </div>
        <p className="mt-1 text-lg text-muted-foreground">{name || "—"}</p>
        {sector && (
          <span className="mt-1 inline-flex rounded-md border px-2 py-0.5 text-xs text-muted-foreground">
            {sector}
          </span>
        )}
      </div>
      <Button
        variant={isInWatchlist ? "default" : "outline"}
        size="sm"
        onClick={onToggleWatchlist}
        className="gap-1.5"
      >
        <StarIcon
          className={cn(
            "size-4",
            isInWatchlist && "fill-current"
          )}
        />
        {isInWatchlist ? "In Watchlist" : "Add to Watchlist"}
      </Button>
    </div>
  );
}
