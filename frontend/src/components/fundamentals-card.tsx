"use client";

import { MetricCard } from "@/components/metric-card";
import { SectionHeading } from "@/components/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import type { FundamentalsResponse, PiotroskiBreakdown } from "@/types/api";

// ─────────────────────────────────────────────────────────────────────────────
// Piotroski segment bar — 9 segments split into 3 color-coded groups
// ─────────────────────────────────────────────────────────────────────────────

const PIOTROSKI_CRITERIA: {
  key: keyof PiotroskiBreakdown;
  label: string;
  group: "profitability" | "leverage" | "efficiency";
}[] = [
  { key: "positive_roa", label: "Positive ROA", group: "profitability" },
  { key: "positive_cfo", label: "Positive CFO", group: "profitability" },
  { key: "improving_roa", label: "Improving ROA", group: "profitability" },
  { key: "accruals", label: "Accruals Quality", group: "profitability" },
  {
    key: "decreasing_leverage",
    label: "Decreasing Debt",
    group: "leverage",
  },
  {
    key: "improving_liquidity",
    label: "Improving Liquidity",
    group: "leverage",
  },
  { key: "no_dilution", label: "No Dilution", group: "leverage" },
  {
    key: "improving_gross_margin",
    label: "Gross Margin ↑",
    group: "efficiency",
  },
  {
    key: "improving_asset_turnover",
    label: "Asset Turnover ↑",
    group: "efficiency",
  },
];

const GROUP_COLORS = {
  profitability: {
    filled: "bg-blue-500",
    empty: "bg-blue-100 dark:bg-blue-950",
  },
  leverage: {
    filled: "bg-emerald-500",
    empty: "bg-emerald-100 dark:bg-emerald-950",
  },
  efficiency: {
    filled: "bg-violet-500",
    empty: "bg-violet-100 dark:bg-violet-950",
  },
} as const;

function piotroskiLabel(score: number): string {
  if (score >= 7) return "Strong";
  if (score >= 4) return "Average";
  return "Weak";
}

function piotroskiColor(score: number): string {
  if (score >= 7) return "text-gain";
  if (score >= 4) return "text-neutral-signal";
  return "text-loss";
}

interface PiotroskiBarProps {
  score: number;
  breakdown: PiotroskiBreakdown;
}

function PiotroskiBar({ score, breakdown }: PiotroskiBarProps) {
  return (
    <div className="space-y-3">
      <div className="flex items-baseline gap-2">
        <span className={`text-2xl font-bold font-mono ${piotroskiColor(score)}`}>
          {score}
          <span className="text-sm font-normal text-muted-foreground">/9</span>
        </span>
        <span className={`text-sm font-medium ${piotroskiColor(score)}`}>
          {piotroskiLabel(score)}
        </span>
      </div>

      {/* Segmented bar */}
      <div className="flex gap-0.5" aria-label={`Piotroski F-Score: ${score} of 9`}>
        {PIOTROSKI_CRITERIA.map(({ key, label, group }) => {
          const filled = breakdown[key] === 1;
          const colors = GROUP_COLORS[group];
          return (
            <div
              key={key}
              title={`${label}: ${filled ? "✓" : "✗"}`}
              className={`h-3 flex-1 rounded-sm transition-colors ${
                filled ? colors.filled : colors.empty
              }`}
            />
          );
        })}
      </div>

      {/* Group legend */}
      <div className="flex gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-sm bg-blue-500" />
          Profitability (4)
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-sm bg-emerald-500" />
          Leverage (3)
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-sm bg-violet-500" />
          Efficiency (2)
        </span>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Metric formatters
// ─────────────────────────────────────────────────────────────────────────────

function fmt(value: number | null, decimals = 1, suffix = ""): string {
  if (value === null || value === undefined) return "N/A";
  return `${value.toFixed(decimals)}${suffix}`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Main card
// ─────────────────────────────────────────────────────────────────────────────

interface FundamentalsCardProps {
  fundamentals: FundamentalsResponse | undefined;
  isLoading: boolean;
}

export function FundamentalsCard({
  fundamentals,
  isLoading,
}: FundamentalsCardProps) {
  if (isLoading) {
    return (
      <div className="space-y-4">
        <SectionHeading>Fundamentals</SectionHeading>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-20 rounded-lg" />
          ))}
        </div>
        <Skeleton className="h-24 rounded-lg" />
      </div>
    );
  }

  if (!fundamentals) {
    return null;
  }

  const hasAnyData =
    fundamentals.pe_ratio !== null ||
    fundamentals.peg_ratio !== null ||
    fundamentals.fcf_yield !== null ||
    fundamentals.debt_to_equity !== null ||
    fundamentals.piotroski_score !== null;

  if (!hasAnyData) {
    return (
      <div className="space-y-4">
        <SectionHeading>Fundamentals</SectionHeading>
        <p className="text-sm text-muted-foreground">
          Fundamental data not available for this ticker (ETF, SPAC, or new listing).
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <SectionHeading>Fundamentals</SectionHeading>

      {/* Valuation metrics row */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricCard
          label="P/E Ratio"
          value={fmt(fundamentals.pe_ratio, 1, "×")}
        />
        <MetricCard
          label="PEG Ratio"
          value={fmt(fundamentals.peg_ratio, 2, "×")}
        />
        <MetricCard
          label="FCF Yield"
          value={
            fundamentals.fcf_yield !== null
              ? `${(fundamentals.fcf_yield * 100).toFixed(1)}%`
              : "N/A"
          }
        />
        <MetricCard
          label="Debt / Equity"
          value={fmt(fundamentals.debt_to_equity, 2, "×")}
        />
      </div>

      {/* Piotroski F-Score */}
      {fundamentals.piotroski_score !== null && (
        <div className="rounded-lg border bg-card p-4">
          <p className="mb-3 text-sm font-medium text-muted-foreground">
            Piotroski F-Score
          </p>
          <PiotroskiBar
            score={fundamentals.piotroski_score}
            breakdown={fundamentals.piotroski_breakdown}
          />
        </div>
      )}
    </div>
  );
}
