"use client";

import type { SystemHealthZone } from "@/types/command-center";
import { StatusDot } from "./status-dot";

interface SystemHealthPanelProps {
  data: SystemHealthZone | null;
}

function normalizeStatus(s: string): "ok" | "degraded" | "down" | "unknown" {
  const lower = s.toLowerCase();
  if (lower === "ok" || lower === "healthy") return "ok";
  if (lower === "degraded") return "degraded";
  if (lower === "down" || lower === "disabled") return "down";
  return "unknown";
}

export function SystemHealthPanel({ data }: SystemHealthPanelProps) {
  if (!data) {
    return (
      <div className="rounded-xl bg-card border border-border p-5">
        <h3 className="text-sm font-medium text-subtle mb-3">System Health</h3>
        <p className="text-xs text-subtle">Unavailable</p>
      </div>
    );
  }

  const overallStatus = normalizeStatus(data.status);

  return (
    <div data-testid="system-health-panel" className="rounded-xl bg-card border border-border p-5">
      <div className="flex items-center gap-2 mb-4">
        <StatusDot status={overallStatus} />
        <h3 className="text-sm font-medium">System Health</h3>
        <span className="ml-auto text-xs text-subtle capitalize">{data.status}</span>
      </div>

      <div className="space-y-3">
        {/* Database */}
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <StatusDot status={data.database.healthy ? "ok" : "down"} size="sm" />
            <span>Database</span>
          </div>
          <span className="font-mono text-subtle">
            {data.database.latency_ms.toFixed(0)}ms
            <span className="ml-2">
              pool {data.database.pool_active}/{data.database.pool_size}
            </span>
          </span>
        </div>

        {/* Redis */}
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <StatusDot status={data.redis.healthy ? "ok" : "down"} size="sm" />
            <span>Redis</span>
          </div>
          <span className="font-mono text-subtle">
            {data.redis.latency_ms.toFixed(0)}ms
            {data.redis.memory_used_mb != null && (
              <span className="ml-2">{data.redis.memory_used_mb.toFixed(0)}MB</span>
            )}
          </span>
        </div>

        {/* MCP */}
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <StatusDot status={data.mcp.healthy ? "ok" : "down"} size="sm" />
            <span>MCP</span>
          </div>
          <span className="font-mono text-subtle">
            {data.mcp.tool_count} tools
            <span className="ml-2">{data.mcp.mode}</span>
          </span>
        </div>

        {/* Celery */}
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <StatusDot
              status={data.celery.workers != null && data.celery.workers > 0 ? "ok" : "unknown"}
              size="sm"
            />
            <span>Celery</span>
          </div>
          <span className="font-mono text-subtle">
            {data.celery.workers ?? "?"} workers
            {data.celery.queued != null && (
              <span className="ml-2">{data.celery.queued} queued</span>
            )}
          </span>
        </div>

        {/* Langfuse */}
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <StatusDot status={data.langfuse.connected ? "ok" : "down"} size="sm" />
            <span>Langfuse</span>
          </div>
          <span className="font-mono text-subtle">
            {data.langfuse.traces_today} traces
          </span>
        </div>
      </div>
    </div>
  );
}
