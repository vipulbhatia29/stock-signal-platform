"use client";

import Link from "next/link";
import { XIcon } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ScoreBadge } from "@/components/score-badge";

interface StockCardProps {
  ticker: string;
  name: string | null;
  sector: string | null;
  score?: number | null;
  onRemove: () => void;
}

export function StockCard({
  ticker,
  name,
  sector,
  score,
  onRemove,
}: StockCardProps) {
  return (
    <Card className="group relative transition-colors hover:border-foreground/20">
      <Button
        variant="ghost"
        size="icon"
        className="absolute top-2 right-2 size-6 opacity-0 group-hover:opacity-100 transition-opacity"
        onClick={(e) => {
          e.preventDefault();
          onRemove();
        }}
        aria-label={`Remove ${ticker}`}
      >
        <XIcon className="size-3.5" />
      </Button>
      <Link href={`/stocks/${ticker}`}>
        <CardHeader className="pb-1">
          <div className="flex items-center justify-between pr-6">
            <span className="font-mono text-base font-semibold">{ticker}</span>
            <ScoreBadge score={score ?? null} size="sm" />
          </div>
        </CardHeader>
        <CardContent className="space-y-1">
          <p className="truncate text-sm text-muted-foreground">
            {name || "—"}
          </p>
          {sector && (
            <span className="inline-flex rounded-md border px-1.5 py-0.5 text-xs text-muted-foreground">
              {sector}
            </span>
          )}
        </CardContent>
      </Link>
    </Card>
  );
}

export function StockCardSkeleton() {
  return (
    <Card>
      <CardHeader className="pb-1">
        <div className="flex items-center justify-between">
          <Skeleton className="h-5 w-16" />
          <Skeleton className="h-5 w-10" />
        </div>
      </CardHeader>
      <CardContent className="space-y-1">
        <Skeleton className="h-4 w-28" />
        <Skeleton className="h-5 w-16" />
      </CardContent>
    </Card>
  );
}
