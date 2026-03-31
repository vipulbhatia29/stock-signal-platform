"use client";

import { useState } from "react";
import type { ApiTrafficDrillDown } from "@/types/command-center-drilldown";

type SortDir = "asc" | "desc";

interface ApiTrafficDetailProps {
  data: ApiTrafficDrillDown;
}

export function ApiTrafficDetail({ data }: ApiTrafficDetailProps) {
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const sorted = [...data.endpoints].sort((a, b) =>
    sortDir === "desc" ? b.count - a.count : a.count - b.count,
  );

  const toggleSort = () => setSortDir((d) => (d === "desc" ? "asc" : "desc"));

  return (
    <div className="space-y-6">
      {/* Summary metrics */}
      <div className="grid grid-cols-3 gap-3">
        <MetricCard
          label="Requests Today"
          value={data.total_requests_today.toLocaleString()}
        />
        <MetricCard
          label="Errors Today"
          value={data.total_errors_today.toLocaleString()}
          alert={data.total_errors_today > 0}
        />
        <MetricCard
          label="p95 Latency"
          value={
            data.latency_p95_ms != null
              ? `${data.latency_p95_ms.toFixed(0)}ms`
              : "\u2014"
          }
        />
      </div>

      {/* Latency detail strip */}
      <div className="flex gap-4 text-xs text-muted-foreground">
        <span>
          p50:{" "}
          {data.latency_p50_ms != null
            ? `${data.latency_p50_ms.toFixed(0)}ms`
            : "\u2014"}
        </span>
        <span>
          p99:{" "}
          {data.latency_p99_ms != null
            ? `${data.latency_p99_ms.toFixed(0)}ms`
            : "\u2014"}
        </span>
        <span>
          Error rate:{" "}
          {data.error_rate_pct != null
            ? `${data.error_rate_pct.toFixed(2)}%`
            : "\u2014"}
        </span>
        <span>Samples: {data.sample_count}</span>
      </div>

      {/* Endpoint table */}
      <div>
        <h3 className="mb-2 text-sm font-medium text-foreground">
          Endpoints ({data.endpoints.length})
        </h3>
        <div className="overflow-x-auto rounded border border-border">
          <table className="w-full text-sm" data-testid="endpoint-table">
            <thead>
              <tr className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground">
                <th className="px-3 py-2">Endpoint</th>
                <th
                  className="cursor-pointer select-none px-3 py-2 text-right"
                  onClick={toggleSort}
                  aria-sort={sortDir === "desc" ? "descending" : "ascending"}
                >
                  Count {sortDir === "desc" ? "\u25BC" : "\u25B2"}
                </th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((ep) => (
                <tr
                  key={ep.endpoint}
                  className="border-b border-border last:border-0 hover:bg-muted/20"
                >
                  <td className="px-3 py-1.5 font-mono text-xs">
                    {ep.endpoint}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {ep.count.toLocaleString()}
                  </td>
                </tr>
              ))}
              {sorted.length === 0 && (
                <tr>
                  <td
                    colSpan={2}
                    className="px-3 py-4 text-center text-muted-foreground"
                  >
                    No endpoint data
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

/* Small metric card used in the summary row */
function MetricCard({
  label,
  value,
  alert,
}: {
  label: string;
  value: string;
  alert?: boolean;
}) {
  return (
    <div className="rounded-md border border-border bg-card p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p
        className={`mt-1 text-lg font-semibold tabular-nums ${alert ? "text-red-400" : "text-foreground"}`}
      >
        {value}
      </p>
    </div>
  );
}
