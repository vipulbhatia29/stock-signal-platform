"use client";

import { useState } from "react";
import type { ApiTrafficZone } from "@/types/command-center";
import type { ApiTrafficDrillDown } from "@/types/command-center-drilldown";
import { useCommandCenterDrillDown } from "@/hooks/use-command-center";
import { MetricCard } from "./metric-card";
import { DrillDownSheet } from "./drill-down-sheet";
import { ApiTrafficDetail } from "./api-traffic-detail";
import { Button } from "@/components/ui/button";

interface ApiTrafficPanelProps {
  data: ApiTrafficZone | null;
}

export function ApiTrafficPanel({ data }: ApiTrafficPanelProps) {
  const [detailOpen, setDetailOpen] = useState(false);
  const { data: drillDown, isFetching, refetch } = useCommandCenterDrillDown<ApiTrafficDrillDown>("api-traffic", detailOpen);
  if (!data) {
    return (
      <div className="rounded-xl bg-card border border-border p-5">
        <h3 className="text-sm font-medium text-subtle mb-3">API Traffic</h3>
        <p className="text-xs text-subtle">Unavailable</p>
      </div>
    );
  }

  const errorStatus =
    data.error_rate_pct != null && data.error_rate_pct > 5
      ? "error"
      : data.error_rate_pct != null && data.error_rate_pct > 1
        ? "warn"
        : "ok";

  return (
    <div data-testid="api-traffic-panel" className="rounded-xl bg-card border border-border p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium">API Traffic</h3>
        <Button variant="secondary" size="sm" onClick={() => setDetailOpen(true)}>
          View Details
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-4">
        <MetricCard
          label="RPS (avg)"
          value={data.rps_avg.toFixed(1)}
        />
        <MetricCard
          label="P95 Latency"
          value={data.latency_p95_ms != null ? `${data.latency_p95_ms.toFixed(0)}ms` : "N/A"}
        />
        <MetricCard
          label="Error Rate"
          value={data.error_rate_pct != null ? `${data.error_rate_pct.toFixed(1)}%` : "N/A"}
          status={errorStatus}
        />
        <MetricCard
          label="Requests Today"
          value={data.total_requests_today.toLocaleString()}
        />
      </div>

      {data.top_endpoints.length > 0 && (
        <div>
          <p className="text-xs text-subtle mb-2">Top Endpoints</p>
          <div className="space-y-1">
            {data.top_endpoints.slice(0, 5).map((ep) => (
              <div key={ep.endpoint} className="flex items-center justify-between text-xs">
                <span className="font-mono text-muted-foreground truncate max-w-[70%]">
                  {ep.endpoint}
                </span>
                <span className="font-mono text-subtle">{ep.count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <DrillDownSheet
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        title="API Traffic Details"
        onRefresh={() => refetch()}
        isRefreshing={isFetching}
      >
        {drillDown ? <ApiTrafficDetail data={drillDown} /> : <p className="text-xs text-subtle">Loading...</p>}
      </DrillDownSheet>
    </div>
  );
}
