"use client";

import { useState } from "react";

interface ToolCardProps {
  tool: string;
  params: Record<string, unknown>;
  status: "running" | "completed" | "error";
  result?: unknown;
}

function getToolSummary(tool: string, result: unknown): string {
  if (!result || typeof result !== "object") return "";
  const r = result as Record<string, unknown>;

  switch (tool) {
    case "analyze_stock":
      return `Score: ${r.composite_score ?? "N/A"} | RSI: ${r.rsi_value ?? "N/A"}`;
    case "screen_stocks":
      return Array.isArray(r.results)
        ? `${r.results.length} stocks found`
        : "Screening complete";
    case "get_analyst_ratings":
      return `Consensus: ${r.consensus ?? "N/A"}`;
    case "compute_signals":
      return `Signal: ${r.signal ?? r.composite_score ?? "N/A"}`;
    case "recommendations":
      return Array.isArray(r.recommendations)
        ? `${r.recommendations.length} recommendations`
        : "Recommendations ready";
    default:
      return "Result ready";
  }
}

export function ToolCard({ tool, params, status, result }: ToolCardProps) {
  const [expanded, setExpanded] = useState(false);

  const paramStr = Object.entries(params)
    .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
    .join(", ");

  return (
    <div
      className={`my-1.5 rounded-md border px-3 py-2 text-xs ${
        status === "error"
          ? "border-destructive/30 bg-destructive/5"
          : status === "running"
            ? "border-border bg-card animate-pulse"
            : "border-border bg-card"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {status === "running" && (
            <svg className="h-3.5 w-3.5 animate-spin text-accent shrink-0" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          )}
          {status === "completed" && (
            <svg className="h-3.5 w-3.5 text-green-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
            </svg>
          )}
          {status === "error" && (
            <svg className="h-3.5 w-3.5 text-destructive shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          )}
          <span className="font-medium text-foreground truncate">{tool}</span>
          <span className="text-muted-foreground truncate">({paramStr})</span>
        </div>
      </div>

      {status === "completed" && result != null && (
        <div className="mt-1.5 text-muted-foreground">
          <span>{getToolSummary(tool, result)}</span>
          <button
            onClick={() => setExpanded(!expanded)}
            className="ml-2 text-accent hover:underline"
          >
            {expanded ? "Hide" : "Show full result"}
          </button>
        </div>
      )}

      {status === "error" && result != null && (
        <div className="mt-1.5 text-destructive">
          {typeof result === "object" && result !== null && "error" in result
            ? String((result as Record<string, unknown>).error)
            : JSON.stringify(result)}
        </div>
      )}

      {expanded && result != null && (
        <pre className="mt-2 max-h-60 overflow-auto rounded bg-background p-2 text-[10px] text-muted-foreground">
          {JSON.stringify(result, null, 2)}
        </pre>
      )}
    </div>
  );
}
