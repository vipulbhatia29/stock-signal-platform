"use client";

import { useState } from "react";
import { ChevronDown, Play, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { PipelineTaskRow } from "./pipeline-task-row";
import type { PipelineGroup, PipelineRun } from "@/hooks/use-admin-pipelines";

interface PipelineGroupCardProps {
  group: PipelineGroup;
  activeRun: PipelineRun | null;
  onTrigger: (group: string) => void;
  isTriggering?: boolean;
}

export function PipelineGroupCard({
  group,
  activeRun,
  onTrigger,
  isTriggering,
}: PipelineGroupCardProps) {
  const [isOpen, setIsOpen] = useState(false);
  const isRunning = activeRun?.status === "running";

  // Build task status map from active run
  const taskStatuses = activeRun?.task_statuses ?? {};

  // Progress info
  const completed = activeRun?.completed ?? 0;
  const failed = activeRun?.failed ?? 0;
  const total = activeRun?.total ?? group.tasks.length;

  return (
    <div className="rounded-lg border border-border bg-card2 overflow-hidden">
      {/* Header — always visible */}
      <div
        role="button"
        tabIndex={0}
        onClick={() => setIsOpen(!isOpen)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setIsOpen(!isOpen);
          }
        }}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-white/[0.02] transition-colors cursor-pointer"
      >
        <div className="flex items-center gap-3">
          <ChevronDown
            className={cn(
              "h-4 w-4 text-subtle transition-transform",
              isOpen && "rotate-180"
            )}
          />
          <div className="text-left">
            <h3 className="text-sm font-semibold text-foreground capitalize">
              {group.name.replace(/_/g, " ")}
            </h3>
            <p className="text-[11px] text-subtle mt-0.5">
              {group.tasks.length} tasks · {group.execution_plan.length} phases
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {isRunning && (
            <span className="text-[11px] text-chart2 font-mono">
              {completed + failed}/{total}
            </span>
          )}
          <button
            onClick={(e) => {
              e.stopPropagation();
              onTrigger(group.name);
            }}
            disabled={isRunning || isTriggering}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors",
              isRunning || isTriggering
                ? "bg-white/[0.04] text-subtle cursor-not-allowed"
                : "bg-chart1/10 text-chart1 hover:bg-chart1/20"
            )}
          >
            {isRunning || isTriggering ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Play className="h-3 w-3" />
            )}
            {isRunning ? "Running" : "Run All"}
          </button>
        </div>
      </div>

      {/* Body — task list by execution phase */}
      {isOpen && (
        <div className="border-t border-border px-4 py-3 space-y-3">
          {group.execution_plan.map((phase, phaseIdx) => (
            <div key={phaseIdx}>
              <div className="text-[9px] uppercase tracking-wider text-subtle mb-1.5">
                Phase {phaseIdx + 1}
              </div>
              <div className="space-y-0.5">
                {phase.map((taskName) => {
                  const task = group.tasks.find((t) => t.name === taskName);
                  if (!task) return null;
                  return (
                    <PipelineTaskRow
                      key={taskName}
                      task={task}
                      status={
                        (taskStatuses[taskName] as
                          | "pending"
                          | "running"
                          | "success"
                          | "failed") ?? "pending"
                      }
                      isParallel={phase.length > 1}
                    />
                  );
                })}
              </div>
            </div>
          ))}

          {/* Error summary */}
          {activeRun && Object.keys(activeRun.errors).length > 0 && (
            <div className="rounded-md bg-loss/10 border border-loss/20 px-3 py-2 mt-2">
              <div className="text-[9px] uppercase tracking-wider text-loss mb-1">
                Errors
              </div>
              {Object.entries(activeRun.errors).map(([task, error]) => (
                <div key={task} className="text-[11px] text-loss/80">
                  <span className="font-mono">{task.split(".").pop()}</span>: {error}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
