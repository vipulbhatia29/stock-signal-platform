"use client";

import { cn } from "@/lib/utils";

interface MetricCardProps {
  label: string;
  value: string | number;
  subtitle?: string;
  status?: "ok" | "warn" | "error";
}

const statusColors: Record<string, string> = {
  ok: "text-emerald-400",
  warn: "text-yellow-400",
  error: "text-red-500",
};

export function MetricCard({ label, value, subtitle, status }: MetricCardProps) {
  return (
    <div
      data-testid="metric-card"
      className="rounded-lg bg-card2 border border-border p-4"
    >
      <p className="text-xs text-subtle mb-1">{label}</p>
      <p
        className={cn(
          "text-2xl font-mono font-semibold tracking-tight",
          status ? statusColors[status] : "text-foreground"
        )}
      >
        {value}
      </p>
      {subtitle && (
        <p className="text-xs text-subtle mt-1">{subtitle}</p>
      )}
    </div>
  );
}
