"use client";

import { useState } from "react";
import type { SystemHealthZone } from "@/types/command-center";
import { StatusDot } from "./status-dot";
import { DrillDownSheet } from "./drill-down-sheet";

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

function formatUptime(seconds: number | null): string {
  if (seconds == null) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

export function SystemHealthPanel({ data }: SystemHealthPanelProps) {
  const [detailOpen, setDetailOpen] = useState(false);

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

      {/* View Details button */}
      <button
        onClick={() => setDetailOpen(true)}
        aria-expanded={detailOpen}
        className="mt-4 text-xs text-cyan hover:text-cyan/80 transition-colors"
      >
        View Details
      </button>

      {/* Drill-down sheet */}
      <DrillDownSheet
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        title="System Health Details"
      >
        <div className="space-y-6">
          {/* Database */}
          <div data-testid="drilldown-database" className="space-y-1">
            <div className="flex items-center gap-2">
              <StatusDot status={data.database.healthy ? "ok" : "down"} size="sm" />
              <span className="text-sm font-medium">Database</span>
            </div>
            <div className="ml-5 space-y-0.5 text-xs text-subtle">
              <p>Latency: {data.database.latency_ms.toFixed(1)}ms</p>
              <p>
                Connection Pool: {data.database.pool_active}/{data.database.pool_size} active
                {data.database.pool_overflow > 0 && (
                  <span className="text-yellow-400 ml-1">({data.database.pool_overflow} overflow)</span>
                )}
              </p>
              {data.database.migration_head && (
                <p>Migration Head: <code className="font-mono">{data.database.migration_head}</code></p>
              )}
            </div>
          </div>

          {/* Redis */}
          <div data-testid="drilldown-redis" className="space-y-1">
            <div className="flex items-center gap-2">
              <StatusDot status={data.redis.healthy ? "ok" : "down"} size="sm" />
              <span className="text-sm font-medium">Redis</span>
            </div>
            <div className="ml-5 space-y-0.5 text-xs text-subtle">
              <p>Latency: {data.redis.latency_ms.toFixed(1)}ms</p>
              <p>
                Memory: {data.redis.memory_used_mb?.toFixed(0) ?? "?"}
                {data.redis.memory_max_mb != null && ` / ${data.redis.memory_max_mb}`} MB
              </p>
              <p>Keys: {data.redis.total_keys?.toLocaleString() ?? "?"}</p>
            </div>
          </div>

          {/* MCP */}
          <div data-testid="drilldown-mcp" className="space-y-1">
            <div className="flex items-center gap-2">
              <StatusDot status={data.mcp.healthy ? "ok" : "down"} size="sm" />
              <span className="text-sm font-medium">MCP Server</span>
            </div>
            <div className="ml-5 space-y-0.5 text-xs text-subtle">
              <p>Tools: {data.mcp.tool_count} registered ({data.mcp.mode})</p>
              <p>Uptime: {formatUptime(data.mcp.uptime_seconds)} ({data.mcp.restarts} restarts)</p>
            </div>
          </div>

          {/* Celery */}
          <div data-testid="drilldown-celery" className="space-y-1">
            <div className="flex items-center gap-2">
              <StatusDot
                status={data.celery.workers != null && data.celery.workers > 0 ? "ok" : "unknown"}
                size="sm"
              />
              <span className="text-sm font-medium">Celery</span>
            </div>
            <div className="ml-5 space-y-0.5 text-xs text-subtle">
              <p>Workers: {data.celery.workers ?? "?"} | Queued: {data.celery.queued ?? "?"}</p>
              <p>Beat: {data.celery.beat_active ? "Active" : "Inactive"}</p>
            </div>
          </div>

          {/* Langfuse */}
          <div data-testid="drilldown-langfuse" className="space-y-1">
            <div className="flex items-center gap-2">
              <StatusDot status={data.langfuse.connected ? "ok" : "down"} size="sm" />
              <span className="text-sm font-medium">Langfuse</span>
            </div>
            <div className="ml-5 space-y-0.5 text-xs text-subtle">
              <p>Traces Today: <span>{data.langfuse.traces_today}</span></p>
              <p>Spans Today: <span>{data.langfuse.spans_today}</span></p>
            </div>
          </div>
        </div>
      </DrillDownSheet>
    </div>
  );
}
