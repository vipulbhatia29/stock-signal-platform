"use client";

import { Skeleton } from "@/components/ui/skeleton";
import { StatusDot } from "@/components/command-center/status-dot";
import type { AdminKpisResult, SubsystemHealth } from "@/types/admin-observability";

/** Human-readable labels for each subsystem key. */
const SUBSYSTEM_LABELS: Record<string, string> = {
  http: "HTTP",
  db: "Database",
  cache: "Cache",
  external_api: "External API",
  celery: "Celery",
  agent: "Agent",
  frontend: "Frontend",
};

/** Extract a one-line stat from the subsystem data. */
function getSubsystemStat(key: string, data: SubsystemHealth): string {
  if (key === "http") {
    const total = data.total_requests as number | undefined;
    const errors = data.error_count as number | undefined;
    if (total != null) return `${total} req, ${errors ?? 0} err`;
  }
  if (key === "celery") {
    const workers = data.worker_count as number | undefined;
    if (workers != null) return `${workers} workers`;
  }
  if (key === "external_api") {
    const providers = data.providers as Record<string, unknown> | undefined;
    if (providers) return `${Object.keys(providers).length} providers`;
  }
  return data.status;
}

function HealthPill({
  subsystemKey,
  name,
  subsystem,
}: {
  subsystemKey: string;
  name: string;
  subsystem: SubsystemHealth;
}) {
  const status =
    subsystem.status === "healthy"
      ? "healthy"
      : subsystem.status === "degraded"
        ? "degraded"
        : "down";

  return (
    <div className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2">
      <StatusDot status={status} size="sm" />
      <span className="text-sm font-medium">{name}</span>
      <span className="text-xs text-muted-foreground">
        {getSubsystemStat(subsystemKey, subsystem)}
      </span>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="flex flex-wrap gap-2">
      {Array.from({ length: 7 }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-36 rounded-lg bg-card2" />
      ))}
    </div>
  );
}

export function HealthStrip({
  data,
  isLoading,
  error,
}: {
  data: AdminKpisResult | undefined;
  isLoading: boolean;
  error: Error | null;
}) {
  if (isLoading) return <LoadingSkeleton />;

  if (error) {
    return (
      <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-400">
        Failed to load system health. Retrying...
      </div>
    );
  }

  if (!data) return null;

  const subsystems = data.subsystems ?? {};
  const entries = Object.entries(subsystems);

  if (entries.length === 0) {
    return (
      <div className="text-sm text-muted-foreground">
        No subsystem data available.
      </div>
    );
  }

  return (
    <div className="flex flex-wrap gap-2">
      {entries.map(([key, subsystem]) => (
        <HealthPill
          key={key}
          subsystemKey={key}
          name={SUBSYSTEM_LABELS[key] ?? key}
          subsystem={subsystem}
        />
      ))}
    </div>
  );
}
