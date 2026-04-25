"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type { AdminExternalsResult } from "@/types/admin-observability";

function fmt(n: number | null, decimals = 1, suffix = ""): string {
  if (n == null) return "—";
  return `${n.toFixed(decimals)}${suffix}`;
}

/** Backend returns success_rate as a 0-1 ratio. Convert to percentage for display. */
function toPercent(ratio: number | null): number | null {
  return ratio != null ? ratio * 100 : null;
}

function successRateColor(pct: number | null): string {
  if (pct == null) return "text-muted-foreground";
  if (pct >= 99) return "text-emerald-400";
  if (pct >= 95) return "text-yellow-400";
  return "text-red-400";
}

export function ProviderRow({ data }: { data: AdminExternalsResult }) {
  const [expanded, setExpanded] = useState(false);
  const { provider, stats, error_breakdown, rate_limit_events } = data;
  const top3 = error_breakdown.slice(0, 3);

  return (
    <div className="rounded-lg border border-border bg-card">
      {/* Summary row */}
      <button
        className="flex w-full items-center gap-4 px-4 py-3 text-left hover:bg-card2/50 transition-colors"
        onClick={() => setExpanded((p) => !p)}
        aria-expanded={expanded}
      >
        <span className="w-5 shrink-0 text-muted-foreground">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
        <span className="w-32 font-medium capitalize">{provider}</span>
        <span className="w-24 text-sm text-muted-foreground">
          {stats.call_count.toLocaleString()} calls
        </span>
        <span
          className={cn(
            "w-24 text-sm font-medium",
            successRateColor(toPercent(stats.success_rate))
          )}
        >
          {fmt(toPercent(stats.success_rate), 1, "%")}
        </span>
        <span className="w-28 text-sm text-muted-foreground">
          p95 {fmt(stats.p95_latency_ms, 0, "ms")}
        </span>
        <span className="w-24 text-sm text-muted-foreground">
          ${fmt(stats.total_cost_usd, 4)}
        </span>
        <span
          className={cn(
            "w-20 text-sm",
            rate_limit_events > 0 ? "text-yellow-400" : "text-muted-foreground"
          )}
        >
          {rate_limit_events} RL
        </span>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-border px-4 pb-4 pt-3">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Recent Errors
          </p>
          {top3.length === 0 ? (
            <p className="text-sm text-muted-foreground">No errors in window.</p>
          ) : (
            <ul className="space-y-1">
              {top3.map((e) => (
                <li key={e.error_reason} className="flex items-center gap-2 text-sm">
                  <span className="text-red-400">{e.count}×</span>
                  <span className="text-muted-foreground">{e.error_reason}</span>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-3 grid grid-cols-3 gap-4 text-xs text-muted-foreground">
            <div>
              <span className="block font-medium text-foreground">
                {fmt(stats.p50_latency_ms, 0, "ms")}
              </span>
              p50 latency
            </div>
            <div>
              <span className="block font-medium text-foreground">
                {stats.error_count}
              </span>
              errors
            </div>
            <div>
              <span className="block font-medium text-foreground">
                {stats.success_count}
              </span>
              successes
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
