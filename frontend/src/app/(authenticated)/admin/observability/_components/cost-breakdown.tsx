"use client";

import { useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { useAdminCosts } from "@/hooks/use-admin-observability";
import type { CostGroup } from "@/types/admin-observability";
import { CostChart } from "./cost-chart";
import { cn } from "@/lib/utils";

export interface CostBreakdownProps {
  /** Reserved for future per-query trace linking when costs endpoint returns trace_ids. */
  onOpenTrace?: (traceId: string) => void;
}

const BY_OPTIONS = [
  { label: "Provider", value: "provider" as const },
  { label: "Model", value: "model" as const },
  { label: "Tier", value: "tier" as const },
  { label: "User", value: "user" as const },
];

const WINDOW_OPTIONS = ["7d", "30d"] as const;
type CostWindow = (typeof WINDOW_OPTIONS)[number];

function TopQueriesTable({
  groups,
  dimensionKey,
}: {
  groups: CostGroup[];
  dimensionKey: string;
}) {
  const top10 = groups
    .slice()
    .sort((a, b) => (b.total_cost_usd ?? 0) - (a.total_cost_usd ?? 0))
    .slice(0, 10);

  if (top10.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">No cost data available.</p>
    );
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-border text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          <th className="py-2 text-left">{dimensionKey}</th>
          <th className="py-2 text-right">Cost</th>
          <th className="py-2 text-right">Calls</th>
          <th className="py-2 text-right">Avg/call</th>
        </tr>
      </thead>
      <tbody>
        {top10.map((row, idx) => {
          const label = String(row[dimensionKey] ?? "unknown");
          return (
            <tr
              key={idx}
              className="border-b border-border/50"
            >
              <td className="py-2 text-left">
                <span>{label}</span>
              </td>
              <td className="py-2 text-right text-foreground">
                ${(row.total_cost_usd ?? 0).toFixed(4)}
              </td>
              <td className="py-2 text-right text-muted-foreground">
                {row.call_count ?? 0}
              </td>
              <td className="py-2 text-right text-muted-foreground">
                ${(row.avg_cost_per_call ?? 0).toFixed(5)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function CostBreakdown({ onOpenTrace }: CostBreakdownProps) {
  const [by, setBy] = useState<"provider" | "model" | "tier" | "user">("provider");
  const [costWindow, setCostWindow] = useState<CostWindow>("7d");

  const { data, isLoading, error } = useAdminCosts(costWindow, by, 50);

  return (
    <section aria-label="Cost Breakdown" className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">Cost Breakdown</h2>
        <div className="flex items-center gap-3">
          <div className="flex gap-1.5">
            {WINDOW_OPTIONS.map((w) => (
              <button
                key={w}
                onClick={() => setCostWindow(w)}
                className={cn(
                  "rounded-md px-2.5 py-1 text-[10px] font-medium transition-colors",
                  costWindow === w
                    ? "bg-card2 text-foreground"
                    : "text-subtle hover:text-muted-foreground"
                )}
              >
                {w}
              </button>
            ))}
          </div>
          <div className="flex gap-1.5">
            {BY_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setBy(opt.value)}
                className={cn(
                  "rounded-full px-3 py-1 text-[10px] font-semibold uppercase tracking-wider transition-colors",
                  by === opt.value
                    ? "bg-cdim text-cyan"
                    : "bg-card2 text-muted-foreground hover:text-foreground"
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {isLoading && (
        <div className="space-y-2">
          <Skeleton className="h-[220px] w-full rounded-lg bg-card2" />
          <Skeleton className="h-48 w-full rounded-lg bg-card2" />
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-400">
          Failed to load cost data. Retrying...
        </div>
      )}

      {!isLoading && !error && data?.result && (
        <>
          {/* Bar chart */}
          <div className="rounded-lg border border-border bg-card p-4">
            <CostChart groups={data.result.groups} dimensionKey={by} />
          </div>

          {/* Top 10 table */}
          <div className="rounded-lg border border-border bg-card p-4">
            <h3 className="mb-3 text-sm font-medium">
              Top 10 by Cost — grouped by {by}
            </h3>
            <TopQueriesTable
              groups={data.result.groups}
              dimensionKey={by}
            />
          </div>
        </>
      )}
    </section>
  );
}
