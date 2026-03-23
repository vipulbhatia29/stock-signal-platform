"use client";

import Link from "next/link";
import {
  ArrowUpRight,
  ArrowDownRight,
  Eye,
  Minus,
  TrendingDown,
  Briefcase,
} from "lucide-react";
import { ScoreBadge } from "@/components/score-badge";
import { cn } from "@/lib/utils";

const ACTION_STYLES: Record<string, {
  icon: typeof ArrowUpRight;
  bg: string;
  text: string;
  border: string;
}> = {
  BUY:   { icon: ArrowUpRight,  bg: "bg-gain/10",    text: "text-gain",    border: "border-gain/20" },
  WATCH: { icon: Eye,           bg: "bg-[var(--cdim)]", text: "text-cyan",    border: "border-[var(--bhi)]" },
  AVOID: { icon: ArrowDownRight, bg: "bg-loss/10",    text: "text-loss",    border: "border-loss/20" },
  HOLD:  { icon: Minus,         bg: "bg-warning/10",  text: "text-warning", border: "border-warning/20" },
  SELL:  { icon: TrendingDown,  bg: "bg-loss/10",     text: "text-loss",    border: "border-loss/20" },
};

interface RecommendationRowProps {
  ticker: string;
  action: string;
  confidence: string;
  compositeScore: number;
  reasoning?: string;
  isHeld?: boolean;
}

export function RecommendationRow({
  ticker,
  action,
  confidence,
  compositeScore,
  reasoning,
  isHeld,
}: RecommendationRowProps) {
  const style = ACTION_STYLES[action] ?? ACTION_STYLES.HOLD;
  const Icon = style.icon;

  return (
    <Link
      href={`/stocks/${ticker}`}
      className="flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-3 transition-colors hover:border-[var(--bhi)] hover:bg-hov"
    >
      {/* Action icon */}
      <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-lg", style.bg)}>
        <Icon className={cn("h-4 w-4", style.text)} />
      </div>

      {/* Content */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm font-bold">{ticker}</span>
          {isHeld && (
            <span className="flex items-center gap-0.5 rounded bg-[var(--cdim)] px-1 py-0.5 text-[8px] font-semibold text-cyan">
              <Briefcase className="h-2.5 w-2.5" /> Held
            </span>
          )}
          <span className={cn("rounded border px-1.5 py-0.5 text-[9px] font-semibold", style.bg, style.text, style.border)}>
            {action}
          </span>
          <span className="text-[9px] text-muted-foreground">{confidence}</span>
        </div>
        {reasoning && (
          <p className="mt-0.5 truncate text-[10px] text-muted-foreground">{reasoning}</p>
        )}
      </div>

      {/* Score */}
      <div className="shrink-0">
        <ScoreBadge score={compositeScore} size="sm" />
      </div>
    </Link>
  );
}
