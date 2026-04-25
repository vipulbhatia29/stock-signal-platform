"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusDot } from "@/components/command-center/status-dot";
import { cn } from "@/lib/utils";
import { useAdminPipelines } from "@/hooks/use-admin-observability";
import type { PipelineRun } from "@/types/admin-observability";
import { formatRelativeTime } from "./shared";

const KNOWN_PIPELINES = [
  "nightly_price_refresh",
  "forecast_refresh",
  "news_sentiment",
  "convergence_snapshot",
  "backtest",
  "data_quality",
  "retention",
];

function statusToHealth(status: string): "healthy" | "degraded" | "down" {
  if (status === "success") return "healthy";
  if (status === "running") return "degraded";
  return "down";
}

function RunRow({ run, isExpanded, onToggle }: {
  run: PipelineRun;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr
        className="cursor-pointer hover:bg-muted/50 transition-colors"
        onClick={onToggle}
      >
        <td className="px-3 py-2">
          <StatusDot status={statusToHealth(run.status)} size="sm" />
        </td>
        <td className="px-3 py-2 text-xs">{formatRelativeTime(run.started_at)}</td>
        <td className="px-3 py-2">
          <Badge
            variant="outline"
            className={cn(
              "text-[10px] px-1.5 py-0",
              run.status === "success" && "text-emerald-400 border-emerald-500/20",
              run.status === "failed" && "text-red-400 border-red-500/20",
              run.status === "running" && "text-yellow-400 border-yellow-500/20",
            )}
          >
            {run.status}
          </Badge>
        </td>
        <td className="px-3 py-2 text-xs text-muted-foreground">
          {run.tickers_succeeded}/{run.tickers_total}
        </td>
        <td className="px-3 py-2 text-xs text-muted-foreground">
          {run.total_duration_seconds != null ? `${run.total_duration_seconds}s` : "—"}
        </td>
      </tr>
      {isExpanded && (
        <tr>
          <td colSpan={5} className="px-3 py-2 bg-muted/30">
            <div className="space-y-1 text-xs">
              {run.error_summary && (
                <p className="text-red-400">Error: {run.error_summary}</p>
              )}
              {run.step_durations && Object.keys(run.step_durations).length > 0 && (
                <div>
                  <span className="font-medium">Step durations:</span>
                  <div className="flex flex-wrap gap-2 mt-1">
                    {Object.entries(run.step_durations).map(([step, dur]) => (
                      <span key={step} className="text-muted-foreground">
                        {step}: {dur}s
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {run.retry_count > 0 && (
                <p className="text-yellow-400">Retries: {run.retry_count}</p>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export function PipelineHealth() {
  const [selectedPipeline, setSelectedPipeline] = useState(KNOWN_PIPELINES[0]);
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);
  const { data, isLoading, error } = useAdminPipelines(selectedPipeline);

  if (error) {
    return (
      <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-400">
        Failed to load pipeline data. Retrying...
      </div>
    );
  }

  const result = data?.result;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <h3 className="text-sm font-semibold">Pipeline Health</h3>
        <select
          value={selectedPipeline}
          onChange={(e) => {
            setSelectedPipeline(e.target.value);
            setExpandedRunId(null);
          }}
          className="rounded-md border border-border bg-card px-2 py-1 text-xs"
          aria-label="Select pipeline"
        >
          {KNOWN_PIPELINES.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-8 w-full rounded" />
          ))}
        </div>
      ) : result ? (
        <>
          {/* Watermark + failure pattern summary */}
          <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
            {result.watermark && (
              <span>
                Last completed: {formatRelativeTime(result.watermark.last_completed_at)}
              </span>
            )}
            {result.ticker_success_rate != null && (
              <span>
                Ticker success rate: {(result.ticker_success_rate * 100).toFixed(1)}%
              </span>
            )}
            {result.failure_pattern.is_currently_failing && (
              <Badge variant="outline" className="text-[10px] text-red-400 border-red-500/20">
                {result.failure_pattern.consecutive_failures} consecutive failures
              </Badge>
            )}
          </div>

          {/* Runs table */}
          <div className="rounded-lg border border-border overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-muted/40 text-xs text-muted-foreground">
                  <th className="px-3 py-1.5 text-left w-8"></th>
                  <th className="px-3 py-1.5 text-left">Started</th>
                  <th className="px-3 py-1.5 text-left">Status</th>
                  <th className="px-3 py-1.5 text-left">Tickers</th>
                  <th className="px-3 py-1.5 text-left">Duration</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {result.runs.map((run) => (
                  <RunRow
                    key={run.id}
                    run={run}
                    isExpanded={expandedRunId === run.id}
                    onToggle={() =>
                      setExpandedRunId(expandedRunId === run.id ? null : run.id)
                    }
                  />
                ))}
                {result.runs.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-3 py-4 text-center text-xs text-muted-foreground">
                      No recent runs found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </div>
  );
}
