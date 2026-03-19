"use client";

import { downloadCSV } from "@/lib/csv-export";

const PINNABLE_TOOLS = new Set([
  "analyze_stock",
  "screen_stocks",
  "portfolio_exposure",
  "get_analyst_ratings",
  "get_economic_series",
  "compute_signals",
  "recommendations",
]);

export function shouldPin(toolName: string): boolean {
  return PINNABLE_TOOLS.has(toolName);
}

interface ArtifactBarProps {
  artifact: {
    tool: string;
    params: Record<string, unknown>;
    data: unknown;
  };
  onDismiss: () => void;
}

function extractCSVData(data: unknown): Record<string, unknown>[] | null {
  if (Array.isArray(data)) return data as Record<string, unknown>[];
  if (data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    if (Array.isArray(d.results)) return d.results as Record<string, unknown>[];
    if (Array.isArray(d.recommendations))
      return d.recommendations as Record<string, unknown>[];
  }
  return null;
}

export function ArtifactBar({ artifact, onDismiss }: ArtifactBarProps) {
  const csvData = extractCSVData(artifact.data);
  const paramStr = Object.entries(artifact.params)
    .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
    .join(", ");

  return (
    <div className="mx-4 mt-2 flex items-center justify-between gap-3 rounded-lg border border-accent/20 bg-accent/5 px-4 py-2.5 text-sm">
      <div className="flex items-center gap-2 min-w-0">
        <svg className="h-4 w-4 shrink-0 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 0 1 6 3.75h2.25A2.25 2.25 0 0 1 10.5 6v2.25a2.25 2.25 0 0 1-2.25 2.25H6a2.25 2.25 0 0 1-2.25-2.25V6ZM3.75 15.75A2.25 2.25 0 0 1 6 13.5h2.25a2.25 2.25 0 0 1 2.25 2.25V18a2.25 2.25 0 0 1-2.25 2.25H6A2.25 2.25 0 0 1 3.75 18v-2.25ZM13.5 6a2.25 2.25 0 0 1 2.25-2.25H18A2.25 2.25 0 0 1 20.25 6v2.25A2.25 2.25 0 0 1 18 10.5h-2.25a2.25 2.25 0 0 1-2.25-2.25V6ZM13.5 15.75a2.25 2.25 0 0 1 2.25-2.25H18a2.25 2.25 0 0 1 2.25 2.25V18A2.25 2.25 0 0 1 18 20.25h-2.25a2.25 2.25 0 0 1-2.25-2.25v-2.25Z" />
        </svg>
        <span className="font-medium text-foreground truncate">{artifact.tool}</span>
        <span className="text-muted-foreground truncate text-xs">({paramStr})</span>
      </div>
      <div className="flex items-center gap-1 shrink-0">
        {csvData && csvData.length > 0 && (
          <button
            onClick={() => downloadCSV(artifact.tool, csvData)}
            className="rounded p-1.5 text-muted-foreground hover:bg-accent/10 hover:text-foreground transition-colors"
            title="Export as CSV"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
            </svg>
          </button>
        )}
        <button
          onClick={onDismiss}
          className="rounded p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
          title="Dismiss"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  );
}
