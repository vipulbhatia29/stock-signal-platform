"use client";

import { useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useAdminErrors } from "@/hooks/use-admin-observability";
import type { ErrorEntry } from "@/types/admin-observability";
import { formatRelativeTime, LAYER_COLORS, LAYER_LABELS, SEVERITY_COLORS } from "./shared";

const TIME_RANGE_OPTIONS = [
  { label: "1h", value: "1h" },
  { label: "6h", value: "6h" },
  { label: "24h", value: "24h" },
];

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

export function LayerPill({ source }: { source: ErrorEntry["source"] }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-medium",
        LAYER_COLORS[source] ?? "bg-muted text-muted-foreground border-border"
      )}
    >
      {LAYER_LABELS[source] ?? source}
    </span>
  );
}

export function SeverityBadge({
  severity,
}: {
  severity: ErrorEntry["severity"];
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-medium capitalize",
        SEVERITY_COLORS[severity] ??
          "bg-muted text-muted-foreground border-border"
      )}
    >
      {severity}
    </span>
  );
}

function TraceButton({
  traceId,
  onOpenTrace,
}: {
  traceId: string;
  onOpenTrace: (id: string) => void;
}) {
  return (
    <button
      onClick={() => onOpenTrace(traceId)}
      title={`Open trace ${traceId}`}
      aria-label={`Open trace ${traceId}`}
      className="ml-auto text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
    >
      trace
    </button>
  );
}

export function ErrorRow({
  entry,
  onOpenTrace,
}: {
  entry: ErrorEntry;
  onOpenTrace: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const msg = entry.message ?? "(no message)";
  const truncated = msg.length > 80 && !expanded;

  return (
    <div className="flex flex-col gap-1 border-b border-border py-2 last:border-0">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span className="tabular-nums">{formatRelativeTime(entry.ts)}</span>
        <LayerPill source={entry.source} />
        <SeverityBadge severity={entry.severity} />
        {entry.trace_id && (
          <TraceButton traceId={entry.trace_id} onOpenTrace={onOpenTrace} />
        )}
      </div>
      <button
        className="text-left text-sm text-foreground"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        {truncated ? `${msg.slice(0, 80)}\u2026` : msg}
      </button>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-3 p-4">
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full rounded bg-card2" />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Filters bar
// ---------------------------------------------------------------------------

export interface Filters {
  layer: string;
  severity: string;
  since: string;
  traceSearch: string;
}

export function FiltersBar({
  filters,
  onChange,
}: {
  filters: Filters;
  onChange: (f: Filters) => void;
}) {
  const set = <K extends keyof Filters>(key: K, val: Filters[K]) =>
    onChange({ ...filters, [key]: val });

  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2 text-xs">
      <select
        aria-label="Filter by layer"
        value={filters.layer}
        onChange={(e) => set("layer", e.target.value)}
        className="rounded border border-border bg-background px-2 py-1 text-xs text-foreground"
      >
        <option value="">All layers</option>
        {Object.entries(LAYER_LABELS).map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>

      <select
        aria-label="Filter by severity"
        value={filters.severity}
        onChange={(e) => set("severity", e.target.value)}
        className="rounded border border-border bg-background px-2 py-1 text-xs text-foreground"
      >
        <option value="">All severities</option>
        <option value="error">Error</option>
        <option value="warning">Warning</option>
      </select>

      <div className="flex overflow-hidden rounded border border-border">
        {TIME_RANGE_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => set("since", opt.value)}
            className={cn(
              "px-2 py-1 text-xs",
              filters.since === opt.value
                ? "bg-primary text-primary-foreground"
                : "bg-background text-muted-foreground hover:bg-muted"
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>

      <input
        type="search"
        aria-label="Search by trace ID"
        placeholder="Trace ID\u2026"
        value={filters.traceSearch}
        onChange={(e) => set("traceSearch", e.target.value)}
        className="w-36 rounded border border-border bg-background px-2 py-1 text-xs text-foreground placeholder:text-muted-foreground"
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ErrorStream({
  onOpenTrace,
}: {
  onOpenTrace: (traceId: string) => void;
}) {
  const [filters, setFilters] = useState<Filters>({
    layer: "",
    severity: "",
    since: "1h",
    traceSearch: "",
  });

  const { data, isLoading, error } = useAdminErrors({
    subsystem: filters.layer || undefined,
    severity: filters.severity || undefined,
    since: filters.since,
  });

  const entries = data?.result.errors ?? [];

  const visible = filters.traceSearch
    ? entries.filter((e) =>
        e.trace_id?.toLowerCase().includes(filters.traceSearch.toLowerCase())
      )
    : entries;

  return (
    <div className="flex flex-col rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="text-sm font-semibold">Live Error Stream</h2>
        <span className="text-xs text-muted-foreground">
          {data?.meta.total_count != null
            ? `${data.meta.total_count} total`
            : ""}
          {data?.meta.truncated ? " (truncated)" : ""}
        </span>
      </div>

      <FiltersBar filters={filters} onChange={setFilters} />

      {isLoading ? (
        <LoadingSkeleton />
      ) : error ? (
        <div className="rounded-b-lg border-red-500/30 bg-red-500/5 p-4 text-sm text-red-400">
          Failed to load error stream. Retrying\u2026
        </div>
      ) : visible.length === 0 ? (
        <div className="p-4 text-sm text-muted-foreground">
          No errors in this window.
        </div>
      ) : (
        <div className="overflow-y-auto px-4" style={{ maxHeight: "28rem" }}>
          {visible.map((entry, i) => (
            <ErrorRow key={`${entry.ts}-${entry.source}-${i}`} entry={entry} onOpenTrace={onOpenTrace} />
          ))}
        </div>
      )}
    </div>
  );
}
