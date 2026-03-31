"use client";

import { cn } from "@/lib/utils";

type StatusLevel = "ok" | "healthy" | "degraded" | "down" | "disabled" | "unknown";

interface StatusDotProps {
  status: StatusLevel;
  size?: "sm" | "md";
}

const colorMap: Record<StatusLevel, string> = {
  ok: "bg-emerald-400",
  healthy: "bg-emerald-400",
  degraded: "bg-yellow-400",
  down: "bg-red-500",
  disabled: "bg-red-500",
  unknown: "bg-zinc-500",
};

const pulseStatuses = new Set<StatusLevel>(["ok", "healthy"]);

export function StatusDot({ status, size = "md" }: StatusDotProps) {
  const sizeClass = size === "sm" ? "h-2 w-2" : "h-2.5 w-2.5";
  const color = colorMap[status] ?? colorMap.unknown;
  const shouldPulse = pulseStatuses.has(status);

  return (
    <span
      data-testid="status-dot"
      data-status={status}
      className={cn(
        "inline-block rounded-full flex-shrink-0",
        sizeClass,
        color,
        shouldPulse && "animate-pulse"
      )}
    />
  );
}
