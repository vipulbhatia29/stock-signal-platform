"use client";

import { useState } from "react";
import type { PipelineRunEntry } from "@/types/command-center-drilldown";
import { StatusDot } from "./status-dot";

const dotStatus = (s: string): "ok" | "degraded" | "down" =>
  s === "success" || s === "completed" ? "ok" : s === "running" ? "degraded" : "down";

interface PipelineDetailProps {
  data: { runs: PipelineRunEntry[]; total: number; days: number };
}

function fmtDuration(seconds: number | null): string {
  if (seconds == null) return "\u2014";
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}m ${secs}s`;
}

export function PipelineDetail({ data }: PipelineDetailProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">
        {data.total} runs over last {data.days} days
      </p>

      <div className="overflow-x-auto rounded border border-border">
        <table className="w-full text-sm" data-testid="pipeline-table">
          <thead>
            <tr className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground">
              <th className="px-3 py-2">Pipeline</th>
              <th className="px-3 py-2">Date</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2 text-right">Duration</th>
              <th className="px-3 py-2 text-right">OK / Fail / Total</th>
            </tr>
          </thead>
          <tbody>
            {data.runs.map((run) => {
              const isExpanded = expandedId === run.id;
              return (
                <PipelineRow
                  key={run.id}
                  run={run}
                  isExpanded={isExpanded}
                  onToggle={() =>
                    setExpandedId(isExpanded ? null : run.id)
                  }
                />
              );
            })}
            {data.runs.length === 0 && (
              <tr>
                <td
                  colSpan={5}
                  className="px-3 py-4 text-center text-muted-foreground"
                >
                  No pipeline runs
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PipelineRow({
  run,
  isExpanded,
  onToggle,
}: {
  run: PipelineRunEntry;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const hasDetail =
    (run.error_summary && Object.keys(run.error_summary).length > 0) ||
    (run.step_durations && Object.keys(run.step_durations).length > 0);

  return (
    <>
      <tr
        className={`border-b border-border last:border-0 ${hasDetail ? "cursor-pointer" : ""} hover:bg-muted/20`}
        onClick={hasDetail ? onToggle : undefined}
        data-testid="pipeline-row"
      >
        <td className="px-3 py-1.5 text-xs">{run.pipeline_name}</td>
        <td className="px-3 py-1.5 text-xs text-muted-foreground">
          {new Date(run.started_at).toLocaleDateString()}
        </td>
        <td className="px-3 py-1.5">
          <span className="flex items-center gap-1.5 text-xs">
            <StatusDot status={dotStatus(run.status)} size="sm" />
            {run.status}
          </span>
        </td>
        <td className="px-3 py-1.5 text-right tabular-nums text-xs">
          {fmtDuration(run.total_duration_seconds)}
        </td>
        <td className="px-3 py-1.5 text-right tabular-nums text-xs">
          {run.tickers_succeeded} / {run.tickers_failed} / {run.tickers_total}
        </td>
      </tr>

      {isExpanded && hasDetail && (
        <tr data-testid="pipeline-row-detail">
          <td colSpan={5} className="bg-muted/10 px-4 py-3">
            {run.step_durations &&
              Object.keys(run.step_durations).length > 0 && (
                <div className="mb-3">
                  <p className="mb-1 text-xs font-medium text-foreground">
                    Step Durations
                  </p>
                  <ul className="space-y-0.5 text-xs text-muted-foreground">
                    {Object.entries(run.step_durations).map(([step, dur]) => (
                      <li key={step} className="flex justify-between">
                        <span>{step}</span>
                        <span className="tabular-nums">
                          {fmtDuration(dur)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

            {run.error_summary &&
              Object.keys(run.error_summary).length > 0 && (
                <div>
                  <p className="mb-1 text-xs font-medium text-red-400">
                    Errors
                  </p>
                  <ul className="space-y-0.5 text-xs text-red-400/80">
                    {Object.entries(run.error_summary).map(([key, msg]) => (
                      <li key={key}>
                        <span className="font-mono">{key}:</span> {msg}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
          </td>
        </tr>
      )}
    </>
  );
}
