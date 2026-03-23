"use client";

import type { ToolCall } from "@/hooks/chat-reducer";

interface PlanDisplayProps {
  steps: string[];
  reasoning: string;
  toolCalls: ToolCall[];
}

export function PlanDisplay({ steps, reasoning, toolCalls }: PlanDisplayProps) {
  const completedTools = new Set(
    toolCalls.filter((tc) => tc.status === "completed").map((tc) => tc.tool)
  );
  const errorTools = new Set(
    toolCalls.filter((tc) => tc.status === "error").map((tc) => tc.tool)
  );

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-3 text-sm">
      <p className="mb-2 font-medium text-[var(--color-foreground)]">
        Researching...
      </p>
      {reasoning && (
        <p className="mb-2 text-[var(--color-muted-foreground)]">{reasoning}</p>
      )}
      <ul className="space-y-1">
        {steps.map((step, i) => {
          const isDone = completedTools.has(step);
          const isError = errorTools.has(step);
          const icon = isDone ? "✓" : isError ? "✗" : "○";
          const color = isDone
            ? "text-[var(--color-gain)]"
            : isError
              ? "text-[var(--color-loss)]"
              : "text-[var(--color-muted-foreground)]";
          return (
            <li key={i} className={`flex items-center gap-2 ${color}`}>
              <span className="w-4 text-center">{icon}</span>
              <span>{step}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
