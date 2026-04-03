"use client";

import { cn } from "@/lib/utils";
import { ShieldAlert } from "lucide-react";
import type { CVaRSummary } from "@/types/api";

interface CVaRCardProps {
  data: CVaRSummary | undefined;
  isLoading: boolean;
}

/** CVaR risk card — "In a bad month" / "In a very bad month" display. */
export function CVaRCard({ data, isLoading }: CVaRCardProps) {
  if (isLoading) {
    return (
      <div className="rounded-lg border border-border bg-card p-4 animate-pulse">
        <div className="h-4 w-24 rounded bg-border mb-3" />
        <div className="space-y-2">
          <div className="h-6 w-40 rounded bg-border" />
          <div className="h-6 w-40 rounded bg-border" />
        </div>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="relative rounded-lg border border-border bg-card p-4 overflow-hidden">
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-loss/50 to-transparent" />
      <div className="flex items-center gap-1.5 mb-3">
        <ShieldAlert className="h-4 w-4 text-warning" aria-hidden="true" />
        <span className="text-[9px] font-semibold uppercase tracking-[0.08em] text-subtle">
          Tail Risk (CVaR)
        </span>
      </div>

      <div className="space-y-3">
        <RiskRow
          label="In a bad month"
          sublabel="1-in-20 scenario"
          value={data.cvar_95_pct}
          severity="moderate"
        />
        <RiskRow
          label="In a very bad month"
          sublabel="1-in-100 scenario"
          value={data.cvar_99_pct}
          severity="severe"
        />
      </div>
    </div>
  );
}

function RiskRow({
  label,
  sublabel,
  value,
  severity,
}: {
  label: string;
  sublabel: string;
  value: number;
  severity: "moderate" | "severe";
}) {
  return (
    <div className="flex items-center justify-between">
      <div>
        <div className="text-sm text-foreground">{label}</div>
        <div className="text-[10px] text-subtle">{sublabel}</div>
      </div>
      <span
        className={cn(
          "font-mono text-lg font-bold",
          severity === "severe" ? "text-loss" : "text-warning",
        )}
      >
        {value.toFixed(1)}%
      </span>
    </div>
  );
}
