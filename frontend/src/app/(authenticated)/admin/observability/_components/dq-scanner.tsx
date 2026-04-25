"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useAdminDq } from "@/hooks/use-admin-observability";
import type { DqFinding } from "@/types/admin-observability";
import { formatRelativeTime, SEVERITY_COLORS } from "./shared";

function FindingRow({ finding }: { finding: DqFinding }) {
  const sevClass = SEVERITY_COLORS[finding.severity] ?? "bg-muted text-muted-foreground border-border";

  return (
    <div className="flex items-start gap-3 rounded-lg border border-border bg-card px-3 py-2">
      <Badge variant="outline" className={cn("text-[10px] px-1.5 py-0 shrink-0 mt-0.5", sevClass)}>
        {finding.severity}
      </Badge>
      <div className="min-w-0 flex-1 space-y-0.5">
        <p className="text-sm font-medium leading-tight">{finding.check_name}</p>
        <p className="text-xs text-muted-foreground truncate">{finding.message}</p>
        <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
          {finding.ticker && <span>Ticker: {finding.ticker}</span>}
          <span>{formatRelativeTime(finding.detected_at)}</span>
        </div>
      </div>
    </div>
  );
}

export function DqScanner() {
  const [severityFilter, setSeverityFilter] = useState<string>("");
  const [sinceFilter, setSinceFilter] = useState("24h");

  const { data, isLoading, error } = useAdminDq({
    severity: severityFilter || undefined,
    since: sinceFilter,
  });

  if (error) {
    return (
      <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-400">
        Failed to load DQ data. Retrying...
      </div>
    );
  }

  const findings = data?.result?.findings ?? [];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Data Quality Scanner</h3>
        <Button
          size="sm"
          variant="outline"
          disabled
          title="Coming soon"
          className="h-7 text-xs"
        >
          Run Now
        </Button>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2">
        <select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value)}
          className="rounded-md border border-border bg-card px-2 py-1 text-xs"
          aria-label="Filter by severity"
        >
          <option value="">All severities</option>
          <option value="critical">Critical</option>
          <option value="warning">Warning</option>
          <option value="info">Info</option>
        </select>
        <div className="flex gap-1">
          {["1h", "6h", "24h", "7d", "30d"].map((t) => (
            <Button
              key={t}
              size="sm"
              variant={sinceFilter === t ? "default" : "outline"}
              onClick={() => setSinceFilter(t)}
              className="h-6 px-2 text-[10px]"
            >
              {t}
            </Button>
          ))}
        </div>
      </div>

      {/* Findings list */}
      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full rounded-lg" />
          ))}
        </div>
      ) : findings.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
          No DQ findings matching current filters.
        </div>
      ) : (
        <div className="space-y-2">
          {findings.map((f, i) => (
            <FindingRow key={`${f.check_name}-${f.ticker}-${i}`} finding={f} />
          ))}
        </div>
      )}

      {/* Summary */}
      {!isLoading && findings.length > 0 && (
        <p className="text-xs text-muted-foreground">
          {findings.length} finding{findings.length !== 1 ? "s" : ""} in last {sinceFilter}
        </p>
      )}
    </div>
  );
}
