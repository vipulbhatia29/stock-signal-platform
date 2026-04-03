"use client";

import { useRunHistory } from "@/hooks/use-admin-pipelines";
import { StatusDot } from "@/components/command-center/status-dot";

const statusToLevel = {
  success: "ok" as const,
  failed: "down" as const,
  running: "degraded" as const,
  partial: "degraded" as const,
};

function formatDuration(start: string, end: string | null): string {
  if (!end) return "—";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  const secs = Math.floor(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  const remSecs = secs % 60;
  return `${mins}m ${remSecs}s`;
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

interface PipelineRunHistoryProps {
  group: string;
}

export function PipelineRunHistory({ group }: PipelineRunHistoryProps) {
  const { data, isLoading } = useRunHistory(group);

  if (isLoading) return <div className="text-sm text-subtle">Loading history...</div>;
  if (!data?.runs.length) return <div className="text-sm text-subtle">No run history</div>;

  return (
    <div className="rounded-lg border border-border bg-card2 overflow-hidden">
      <div className="px-4 py-2.5 border-b border-border">
        <h4 className="text-[9px] uppercase tracking-wider text-subtle">
          Run History — {group.replace(/_/g, " ")}
        </h4>
      </div>
      <div className="divide-y divide-border">
        {data.runs.map((run) => (
          <div key={run.run_id} className="flex items-center gap-3 px-4 py-2.5 text-[11px]">
            <StatusDot
              status={
                statusToLevel[run.status as keyof typeof statusToLevel] ?? "unknown"
              }
              size="sm"
            />
            <span className="text-foreground font-medium capitalize w-16">
              {run.status}
            </span>
            <span className="text-subtle">{formatTime(run.started_at)}</span>
            <span className="text-subtle ml-auto font-mono">
              {run.completed}/{run.total} tasks
            </span>
            <span className="text-subtle font-mono w-16 text-right">
              {formatDuration(run.started_at, run.completed_at)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
