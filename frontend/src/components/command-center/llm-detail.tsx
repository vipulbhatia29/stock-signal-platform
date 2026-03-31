"use client";

import type {
  LlmDrillDown,
  LlmModelBreakdown,
} from "@/types/command-center-drilldown";

interface LlmDetailProps {
  data: LlmDrillDown;
}

function fmtCost(usd: number): string {
  return usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(2)}`;
}

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export function LlmDetail({ data }: LlmDetailProps) {
  return (
    <div className="space-y-6">
      {/* Model breakdown table */}
      <div>
        <h3 className="mb-2 text-sm font-medium text-foreground">
          Model Breakdown ({data.total_models})
        </h3>
        <div className="overflow-x-auto rounded border border-border">
          <table
            className="w-full text-sm"
            data-testid="model-table"
          >
            <thead>
              <tr className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground">
                <th className="px-3 py-2">Model</th>
                <th className="px-3 py-2">Provider</th>
                <th className="px-3 py-2 text-right">Calls</th>
                <th className="px-3 py-2 text-right">Cost</th>
                <th className="px-3 py-2 text-right">Avg Latency</th>
                <th className="px-3 py-2 text-right">Errors</th>
                <th className="px-3 py-2 text-right">Tokens</th>
              </tr>
            </thead>
            <tbody>
              {data.models.map((m: LlmModelBreakdown) => (
                <tr
                  key={`${m.provider}-${m.model}`}
                  className="border-b border-border last:border-0 hover:bg-muted/20"
                >
                  <td className="px-3 py-1.5 font-mono text-xs">{m.model}</td>
                  <td className="px-3 py-1.5 text-xs text-muted-foreground">
                    {m.provider}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {m.call_count}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {fmtCost(m.total_cost_usd)}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {m.avg_latency_ms.toFixed(0)}ms
                  </td>
                  <td
                    className={`px-3 py-1.5 text-right tabular-nums ${m.error_count > 0 ? "text-red-400" : ""}`}
                  >
                    {m.error_count}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums text-xs">
                    {fmtTokens(m.total_prompt_tokens)} /{" "}
                    {fmtTokens(m.total_completion_tokens)}
                  </td>
                </tr>
              ))}
              {data.models.length === 0 && (
                <tr>
                  <td
                    colSpan={7}
                    className="px-3 py-4 text-center text-muted-foreground"
                  >
                    No model data
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Cascade log */}
      <div>
        <h3 className="mb-2 text-sm font-medium text-foreground">
          Cascade Log ({data.cascades.length})
        </h3>
        <div
          className="max-h-64 overflow-y-auto rounded border border-border"
          data-testid="cascade-log"
        >
          {data.cascades.length === 0 ? (
            <p className="px-3 py-4 text-center text-sm text-muted-foreground">
              No cascades recorded
            </p>
          ) : (
            <ul className="divide-y divide-border">
              {data.cascades.map((c, i) => (
                <li key={i} className="px-3 py-2">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="font-mono text-xs text-foreground">
                      {c.model}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {new Date(c.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                  <p className="mt-0.5 text-xs text-red-400">{c.error}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
