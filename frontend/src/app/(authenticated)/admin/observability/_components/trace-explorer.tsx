"use client";

import { useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { useAdminTrace } from "@/hooks/use-admin-observability";
import type { FlatSpan, SpanNode } from "@/types/admin-observability";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SPAN_KIND_COLORS: Record<string, string> = {
  http: "bg-blue-500",
  http_error: "bg-red-500",
  external_api: "bg-orange-500",
  "db.query": "bg-purple-500",
  auth: "bg-green-500",
  oauth: "bg-emerald-500",
  "agent.intent": "bg-indigo-500",
  "agent.reasoning": "bg-pink-500",
  cache: "bg-teal-500",
};

const SPAN_KIND_LEGEND_COLORS: Record<string, string> = {
  http: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  http_error: "bg-red-500/20 text-red-400 border-red-500/30",
  external_api: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  "db.query": "bg-purple-500/20 text-purple-400 border-purple-500/30",
  auth: "bg-green-500/20 text-green-400 border-green-500/30",
  oauth: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  "agent.intent": "bg-indigo-500/20 text-indigo-400 border-indigo-500/30",
  "agent.reasoning": "bg-pink-500/20 text-pink-400 border-pink-500/30",
  cache: "bg-teal-500/20 text-teal-400 border-teal-500/30",
};

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function flattenSpanTree(node: SpanNode, depth: number): FlatSpan[] {
  const flat: FlatSpan = {
    span_id: node.span_id,
    parent_span_id: node.parent_span_id,
    kind: node.kind,
    ts: node.ts,
    latency_ms: node.latency_ms,
    details: node.details,
    depth,
  };
  const children = (node.children ?? []).flatMap((c) =>
    flattenSpanTree(c, depth + 1)
  );
  return [flat, ...children];
}

function formatTickLabel(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function getTickInterval(totalMs: number): number {
  if (totalMs < 100) return 10;
  if (totalMs < 1000) return 100;
  if (totalMs < 5000) return 500;
  if (totalMs < 10000) return 1000;
  return 2000;
}

// ---------------------------------------------------------------------------
// Sub-component: SpanDetailPanel
// ---------------------------------------------------------------------------

function SpanDetailPanel({
  span,
  traceId,
  onClose,
}: {
  span: FlatSpan;
  traceId: string;
  onClose: () => void;
}) {
  const handleCopy = () => {
    void navigator.clipboard.writeText(traceId);
  };

  return (
    <div className="rounded-lg border border-border bg-card2 p-4 text-xs">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-semibold text-foreground">Span Detail</span>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={handleCopy}>
            Copy trace_id
          </Button>
          <Button variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
      <div className="space-y-1.5">
        <DetailRow label="span_id" value={span.span_id} />
        <DetailRow label="kind" value={span.kind} />
        <DetailRow label="duration" value={span.latency_ms != null ? `${span.latency_ms}ms` : "?"} />
        <DetailRow label="ts" value={span.ts ?? "—"} />
        {span.parent_span_id && (
          <DetailRow label="parent_span_id" value={span.parent_span_id} />
        )}
        {Object.entries(span.details).map(([k, v]) => (
          <DetailRow key={k} label={k} value={String(v ?? "—")} />
        ))}
      </div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <span className="w-36 shrink-0 text-muted-foreground">{label}</span>
      <span className="break-all text-foreground">{value}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: ColorLegend
// ---------------------------------------------------------------------------

function ColorLegend({ kinds }: { kinds: string[] }) {
  if (kinds.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5 px-4 pb-3 pt-1">
      {kinds.map((kind) => (
        <span
          key={kind}
          className={cn(
            "inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-medium",
            SPAN_KIND_LEGEND_COLORS[kind] ?? "bg-muted text-muted-foreground border-border"
          )}
        >
          {kind}
        </span>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: TimeAxis
// ---------------------------------------------------------------------------

function TimeAxis({ totalMs }: { totalMs: number }) {
  if (totalMs <= 0) return null;
  const interval = getTickInterval(totalMs);
  const ticks: number[] = [];
  for (let t = 0; t <= totalMs; t += interval) {
    ticks.push(t);
  }

  return (
    <div className="relative mb-1 h-5 border-b border-border">
      {ticks.map((t) => {
        const pct = (t / totalMs) * 100;
        return (
          <span
            key={t}
            className="absolute -translate-x-1/2 text-[10px] text-muted-foreground"
            style={{ left: `${pct}%` }}
          >
            {formatTickLabel(t)}
          </span>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: SpanRow
// ---------------------------------------------------------------------------

function SpanRow({
  span,
  traceStartMs,
  totalMs,
  isSelected,
  onClick,
}: {
  span: FlatSpan;
  traceStartMs: number;
  totalMs: number;
  isSelected: boolean;
  onClick: () => void;
}) {
  const spanStartMs =
    span.ts != null ? new Date(span.ts).getTime() - traceStartMs : 0;
  const spanDurationMs = span.latency_ms ?? 0;
  const safeTotal = totalMs > 0 ? totalMs : 1;

  const leftPct = Math.max(0, (spanStartMs / safeTotal) * 100);
  const widthPct = Math.max(1, (spanDurationMs / safeTotal) * 100);
  const barColor = SPAN_KIND_COLORS[span.kind] ?? "bg-slate-500";

  return (
    <button
      className={cn(
        "group flex w-full items-center gap-2 rounded px-2 py-0.5 text-left transition-colors hover:bg-muted/50",
        isSelected && "bg-muted"
      )}
      style={{ height: "32px" }}
      onClick={onClick}
      title={`${span.kind} — ${spanDurationMs}ms`}
    >
      {/* Depth indent + label */}
      <div
        className="flex min-w-0 shrink-0 items-center text-xs text-muted-foreground"
        style={{ width: "160px", paddingLeft: `${span.depth * 16}px` }}
      >
        <span className="truncate">{span.kind}</span>
        <span className="ml-1 shrink-0 text-[10px]">
          {span.latency_ms != null ? `${span.latency_ms}ms` : "?"}
        </span>
      </div>

      {/* Waterfall bar area */}
      <div className="relative flex-1" style={{ height: "14px" }}>
        <div
          className={cn("absolute top-0 h-full rounded-sm opacity-80 group-hover:opacity-100", barColor)}
          style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
        />
      </div>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: WaterfallTimeline
// ---------------------------------------------------------------------------

function WaterfallTimeline({
  flatSpans,
  totalDurationMs,
  selectedSpanId,
  onSelectSpan,
}: {
  flatSpans: FlatSpan[];
  totalDurationMs: number;
  selectedSpanId: string | null;
  onSelectSpan: (span: FlatSpan) => void;
}) {
  const traceStartMs =
    flatSpans.length > 0
      ? Math.min(
          ...flatSpans
            .filter((s) => s.ts != null)
            .map((s) => new Date(s.ts!).getTime())
        )
      : 0;

  return (
    <div>
      <div className="px-2">
        <TimeAxis totalMs={totalDurationMs} />
      </div>
      <div className="max-h-[600px] overflow-y-auto">
        {flatSpans.map((span) => (
          <SpanRow
            key={span.span_id}
            span={span}
            traceStartMs={traceStartMs}
            totalMs={totalDurationMs}
            isSelected={selectedSpanId === span.span_id}
            onClick={() => onSelectSpan(span)}
          />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component: TraceExplorer
// ---------------------------------------------------------------------------

export function TraceExplorer({
  initialTraceId,
}: {
  initialTraceId: string | null;
}) {
  // When initialTraceId changes (from "Open Trace" in Zones 2/3), reflect it in
  // the input and trigger a fetch. We track the last seen value in state so we
  // can detect a new arrival without using effects or refs.
  const [lastSeenInitial, setLastSeenInitial] = useState<string | null>(initialTraceId);
  const [inputValue, setInputValue] = useState(initialTraceId ?? "");
  const [submittedTraceId, setSubmittedTraceId] = useState(initialTraceId ?? "");
  const [selectedSpan, setSelectedSpan] = useState<FlatSpan | null>(null);

  if (initialTraceId !== null && initialTraceId !== lastSeenInitial) {
    setLastSeenInitial(initialTraceId);
    setInputValue(initialTraceId);
    setSubmittedTraceId(initialTraceId);
    setSelectedSpan(null);
  }

  const { data, isLoading, error } = useAdminTrace(submittedTraceId);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = inputValue.trim();
    if (trimmed) {
      setSubmittedTraceId(trimmed);
      setSelectedSpan(null);
    }
  };

  // Compute flat spans
  const result = data?.result;
  const flatSpans: FlatSpan[] = (() => {
    if (!result) return [];
    if (result.root_span) {
      return flattenSpanTree(result.root_span, 0);
    }
    if (result.flat_spans) {
      return result.flat_spans.map((s) => ({ ...s, depth: 0 }));
    }
    return [];
  })();

  // Wall-clock range: max(ts + latency_ms) - min(ts)
  const totalDurationMs = (() => {
    const spansWithTs = flatSpans.filter((s) => s.ts != null);
    if (spansWithTs.length === 0) return 0;
    const earliest = Math.min(...spansWithTs.map((s) => new Date(s.ts!).getTime()));
    const latest = Math.max(
      ...spansWithTs.map((s) => new Date(s.ts!).getTime() + (s.latency_ms ?? 0))
    );
    return Math.max(1, latest - earliest);
  })();

  // Compute unique kinds for legend
  const uniqueKinds = Array.from(new Set(flatSpans.map((s) => s.kind)));

  return (
    <div className="flex flex-col gap-4">
      {/* Input bar */}
      <div className="rounded-lg border border-border bg-card">
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold">Trace Explorer</h2>
        </div>
        <form onSubmit={handleSubmit} className="flex items-center gap-2 px-4 py-3">
          <Input
            placeholder="Enter trace ID…"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            className="flex-1 text-sm"
            aria-label="Trace ID"
          />
          <Button type="submit" size="sm" disabled={!inputValue.trim()}>
            Load
          </Button>
        </form>
        {flatSpans.length > 0 && <ColorLegend kinds={uniqueKinds} />}
      </div>

      {/* Results */}
      {submittedTraceId && (
        <div className="rounded-lg border border-border bg-card">
          {isLoading ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-8 w-full rounded bg-card2" />
              ))}
            </div>
          ) : error ? (
            <div className="p-4 text-sm text-red-400">
              Failed to load trace. The trace may not exist or the backend is unreachable.
            </div>
          ) : flatSpans.length === 0 ? (
            <div className="p-4 text-sm text-muted-foreground">
              No spans found for this trace.
            </div>
          ) : (
            <div className="p-2">
              <div className="mb-1 flex items-center justify-between px-2 py-1">
                <span className="text-xs text-muted-foreground">
                  {flatSpans.length} spans
                </span>
                {result && (
                  <Badge variant="outline" className="text-xs font-mono">
                    {result.trace_id.slice(0, 8)}&hellip;
                  </Badge>
                )}
              </div>
              <WaterfallTimeline
                flatSpans={flatSpans}
                totalDurationMs={totalDurationMs}
                selectedSpanId={selectedSpan?.span_id ?? null}
                onSelectSpan={setSelectedSpan}
              />
            </div>
          )}
        </div>
      )}

      {/* Span detail panel */}
      {selectedSpan && result && (
        <SpanDetailPanel
          span={selectedSpan}
          traceId={result.trace_id}
          onClose={() => setSelectedSpan(null)}
        />
      )}
    </div>
  );
}
