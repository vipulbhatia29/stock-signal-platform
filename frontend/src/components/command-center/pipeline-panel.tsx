"use client";

import { useState } from "react";
import type { PipelineZone } from "@/types/command-center";
import type { PipelineDrillDown } from "@/types/command-center-drilldown";
import { useCommandCenterDrillDown } from "@/hooks/use-command-center";
import { StatusDot } from "./status-dot";
import { DrillDownSheet } from "./drill-down-sheet";
import { PipelineDetail } from "./pipeline-detail";
import { Button } from "@/components/ui/button";

interface PipelinePanelProps {
  data: PipelineZone | null;
}

function formatDuration(seconds: number | null): string {
  if (seconds == null) return "N/A";
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}m ${secs}s`;
}

function formatRelativeTime(isoString: string): string {
  const diff = new Date(isoString).getTime() - Date.now();
  if (diff < 0) return "overdue";
  const hours = Math.floor(diff / 3600000);
  const mins = Math.floor((diff % 3600000) / 60000);
  if (hours > 0) return `in ${hours}h ${mins}m`;
  return `in ${mins}m`;
}

export function PipelinePanel({ data }: PipelinePanelProps) {
  const [detailOpen, setDetailOpen] = useState(false);
  const { data: drillDown, isFetching, refetch } = useCommandCenterDrillDown<PipelineDrillDown>("pipeline", detailOpen);
  if (!data) {
    return (
      <div className="rounded-xl bg-card border border-border p-5">
        <h3 className="text-sm font-medium text-subtle mb-3">Pipeline</h3>
        <p className="text-xs text-subtle">Unavailable</p>
      </div>
    );
  }

  const lastRun = data.last_run;
  const runStatus =
    lastRun?.status === "success" || lastRun?.status === "completed"
      ? "ok"
      : lastRun?.status === "running"
        ? "degraded"
        : lastRun
          ? "down"
          : "unknown";

  return (
    <div data-testid="pipeline-panel" className="rounded-xl bg-card border border-border p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium">Pipeline</h3>
        <Button variant="secondary" size="sm" onClick={() => setDetailOpen(true)}>
          View Details
        </Button>
      </div>

      {/* Last run */}
      {lastRun ? (
        <div className="mb-4">
          <div className="flex items-center gap-2 mb-2">
            <StatusDot status={runStatus} size="sm" />
            <span className="text-xs font-medium capitalize">{lastRun.status}</span>
            <span className="text-xs text-subtle ml-auto">
              {formatDuration(lastRun.total_duration_seconds)}
            </span>
          </div>
          <div className="grid grid-cols-3 gap-2 text-center">
            <div>
              <p className="text-lg font-mono font-semibold text-emerald-400">
                {lastRun.tickers_succeeded}
              </p>
              <p className="text-[10px] text-subtle">Success</p>
            </div>
            <div>
              <p className="text-lg font-mono font-semibold text-red-400">
                {lastRun.tickers_failed}
              </p>
              <p className="text-[10px] text-subtle">Failed</p>
            </div>
            <div>
              <p className="text-lg font-mono font-semibold text-muted-foreground">
                {lastRun.tickers_total}
              </p>
              <p className="text-[10px] text-subtle">Total</p>
            </div>
          </div>
        </div>
      ) : (
        <p className="text-xs text-subtle mb-4">No recent runs</p>
      )}

      {/* Next run */}
      {data.next_run_at && (
        <div className="mb-4 text-xs">
          <span className="text-subtle">Next run: </span>
          <span className="font-mono">{formatRelativeTime(data.next_run_at)}</span>
        </div>
      )}

      {/* Watermarks */}
      {data.watermarks.length > 0 && (
        <div>
          <p className="text-xs text-subtle mb-2">Data Watermarks</p>
          <div className="space-y-1">
            {data.watermarks.map((wm) => (
              <div key={wm.pipeline} className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">{wm.pipeline}</span>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-subtle">{wm.last_date}</span>
                  <StatusDot
                    status={wm.status === "current" ? "ok" : "degraded"}
                    size="sm"
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <DrillDownSheet
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        title="Pipeline Details"
        onRefresh={() => refetch()}
        isRefreshing={isFetching}
      >
        {drillDown ? <PipelineDetail data={drillDown} /> : <p className="text-xs text-subtle">Loading...</p>}
      </DrillDownSheet>
    </div>
  );
}
