"use client";

import { StatusDot } from "@/components/command-center/status-dot";
import type { TaskDefinition } from "@/hooks/use-admin-pipelines";

// Map task status to StatusDot status level
type TaskStatus = "pending" | "running" | "success" | "failed";

const statusMap: Record<TaskStatus, "unknown" | "degraded" | "ok" | "down"> = {
  pending: "unknown",
  running: "degraded",
  success: "ok",
  failed: "down",
};

interface PipelineTaskRowProps {
  task: TaskDefinition;
  status?: TaskStatus;
  isParallel?: boolean; // Show parallel indicator
}

export function PipelineTaskRow({
  task,
  status = "pending",
  isParallel = false,
}: PipelineTaskRowProps) {
  return (
    <div className="flex items-center gap-3 px-3 py-2 rounded-md hover:bg-white/[0.03] transition-colors">
      <StatusDot status={statusMap[status]} size="sm" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-foreground truncate">
            {task.display_name}
          </span>
          {isParallel && (
            <span className="text-[9px] uppercase tracking-wider text-subtle px-1.5 py-0.5 rounded bg-white/[0.04]">
              parallel
            </span>
          )}
          {task.is_seed && (
            <span className="text-[9px] uppercase tracking-wider text-chart2 px-1.5 py-0.5 rounded bg-chart2/10">
              seed
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 text-[11px] text-subtle mt-0.5">
          {task.estimated_duration && <span>{task.estimated_duration}</span>}
          {task.schedule && <span>{task.schedule}</span>}
        </div>
      </div>
    </div>
  );
}
