"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import {
  useAdminFindings,
  useAcknowledgeFinding,
  useSuppressFinding,
} from "@/hooks/use-admin-observability";
import type { Finding, FindingSeverity } from "@/types/admin-observability";
import type { OpenTraceFn } from "../observability-admin-client";
import { formatRelativeTime, LAYER_COLORS, SEVERITY_COLORS } from "./shared";

const SEVERITY_BORDER: Record<FindingSeverity, string> = {
  critical: "border-l-red-500",
  error: "border-l-orange-500",
  warning: "border-l-yellow-500",
  info: "border-l-blue-500",
};

function truncate(str: string | null, max: number): string {
  if (!str) return "";
  return str.length > max ? str.slice(0, max) + "..." : str;
}

function FindingCard({
  finding,
  onAcknowledge,
  onSuppress,
  onOpenTrace,
  isAcking,
  isSuppressing,
}: {
  finding: Finding;
  onAcknowledge: () => void;
  onSuppress: () => void;
  onOpenTrace: () => void;
  isAcking: boolean;
  isSuppressing: boolean;
}) {
  const isMuted =
    finding.status === "acknowledged" || finding.status === "suppressed";
  const hasTraces =
    finding.related_traces != null && finding.related_traces.length > 0;
  const evidenceEntries = finding.evidence
    ? Object.entries(finding.evidence).slice(0, 3)
    : [];
  const severity = finding.severity;
  const layerColor = LAYER_COLORS[finding.attribution_layer] ?? "bg-muted text-muted-foreground border-border";

  return (
    <div
      className={cn(
        "rounded-lg border border-border border-l-4 bg-card p-4 space-y-2",
        SEVERITY_BORDER[severity],
        isMuted && "opacity-60"
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="font-semibold text-sm leading-tight">
          {finding.title}
        </span>
        <div className="flex items-center gap-1.5 shrink-0">
          <Badge
            variant="outline"
            className={cn("text-[10px] px-1.5 py-0", layerColor)}
          >
            {finding.attribution_layer}
          </Badge>
          <Badge
            variant="outline"
            className={cn("text-[10px] px-1.5 py-0", SEVERITY_COLORS[severity])}
          >
            {severity}
          </Badge>
        </div>
      </div>

      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span>{formatRelativeTime(finding.opened_at)}</span>
        {finding.status === "acknowledged" && (
          <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
            Acknowledged
          </Badge>
        )}
        {finding.status === "suppressed" && (
          <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
            Suppressed
          </Badge>
        )}
      </div>

      {evidenceEntries.length > 0 && (
        <div className="text-xs text-muted-foreground space-y-0.5">
          {evidenceEntries.map(([key, value]) => (
            <div key={key}>
              <span className="font-medium">{key}:</span>{" "}
              {String(value)}
            </div>
          ))}
        </div>
      )}

      {finding.remediation_hint && (
        <p className="text-xs text-muted-foreground">
          {truncate(finding.remediation_hint, 150)}
        </p>
      )}

      <div className="flex items-center gap-2 pt-1">
        <Button
          size="sm"
          variant="outline"
          onClick={onAcknowledge}
          disabled={isMuted || isAcking}
          className="h-7 text-xs"
        >
          {isAcking ? "..." : "Acknowledge"}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={onSuppress}
          disabled={isMuted || isSuppressing}
          className="h-7 text-xs"
        >
          {isSuppressing ? "..." : "Suppress 1h"}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={onOpenTrace}
          disabled={!hasTraces}
          className="h-7 text-xs"
        >
          Open Trace
        </Button>
      </div>
    </div>
  );
}

function FindingCardSkeleton() {
  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-2">
      <Skeleton className="h-4 w-3/4" />
      <Skeleton className="h-3 w-1/4" />
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-2/3" />
      <div className="flex gap-2 pt-1">
        <Skeleton className="h-7 w-24" />
        <Skeleton className="h-7 w-24" />
        <Skeleton className="h-7 w-24" />
      </div>
    </div>
  );
}

export function AnomalyFindings({ onOpenTrace }: { onOpenTrace: OpenTraceFn }) {
  const [statusFilter, setStatusFilter] = useState("open");
  const [severityFilter, setSeverityFilter] = useState<string>("all");

  const { data, isLoading, error } = useAdminFindings({
    status: statusFilter !== "all" ? statusFilter : undefined,
    severity: severityFilter !== "all" ? severityFilter : undefined,
  });

  const acknowledgeMutation = useAcknowledgeFinding();
  const suppressMutation = useSuppressFinding();

  const findings = data?.result?.findings ?? [];

  if (error) {
    return (
      <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-400">
        Failed to load findings. Retrying...
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Select value={statusFilter} onValueChange={(v) => { if (v) setStatusFilter(v); }}>
          <SelectTrigger size="sm" className="w-[140px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="open">Open</SelectItem>
            <SelectItem value="acknowledged">Acknowledged</SelectItem>
            <SelectItem value="resolved">Resolved</SelectItem>
            <SelectItem value="suppressed">Suppressed</SelectItem>
            <SelectItem value="all">All</SelectItem>
          </SelectContent>
        </Select>
        <Select value={severityFilter} onValueChange={(v) => { if (v) setSeverityFilter(v); }}>
          <SelectTrigger size="sm" className="w-[140px]">
            <SelectValue placeholder="Severity" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All</SelectItem>
            <SelectItem value="critical">Critical</SelectItem>
            <SelectItem value="error">Error</SelectItem>
            <SelectItem value="warning">Warning</SelectItem>
            <SelectItem value="info">Info</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          <FindingCardSkeleton />
          <FindingCardSkeleton />
          <FindingCardSkeleton />
        </div>
      ) : findings.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
          No findings matching current filters.
        </div>
      ) : (
        <div className="space-y-3">
          {findings.map((finding) => (
            <FindingCard
              key={finding.id}
              finding={finding}
              onAcknowledge={() =>
                acknowledgeMutation.mutate(finding.id)
              }
              onSuppress={() =>
                suppressMutation.mutate(finding.id)
              }
              onOpenTrace={() => {
                const firstTrace = finding.related_traces?.[0];
                if (firstTrace) onOpenTrace(firstTrace);
              }}
              isAcking={acknowledgeMutation.isPending && acknowledgeMutation.variables === finding.id}
              isSuppressing={suppressMutation.isPending && suppressMutation.variables === finding.id}
            />
          ))}
        </div>
      )}
    </div>
  );
}
