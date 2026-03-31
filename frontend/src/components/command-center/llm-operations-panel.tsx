"use client";

import { useState } from "react";
import type { LlmOperationsZone } from "@/types/command-center";
import type { LlmDrillDown } from "@/types/command-center-drilldown";
import { useCommandCenterDrillDown } from "@/hooks/use-command-center";
import { StatusDot } from "./status-dot";
import { GaugeBar } from "./gauge-bar";
import { MetricCard } from "./metric-card";
import { DrillDownSheet } from "./drill-down-sheet";
import { LlmDetail } from "./llm-detail";
import { Button } from "@/components/ui/button";

interface LlmOperationsPanelProps {
  data: LlmOperationsZone | null;
}

function costDelta(today: number, yesterday: number): string {
  if (yesterday === 0) return "";
  const pctChange = ((today - yesterday) / yesterday) * 100;
  const sign = pctChange >= 0 ? "+" : "";
  return `${sign}${pctChange.toFixed(0)}% vs yesterday`;
}

export function LlmOperationsPanel({ data }: LlmOperationsPanelProps) {
  const [detailOpen, setDetailOpen] = useState(false);
  const { data: drillDown, isFetching, refetch } = useCommandCenterDrillDown<LlmDrillDown>("llm", detailOpen);
  if (!data) {
    return (
      <div className="rounded-xl bg-card border border-border p-5">
        <h3 className="text-sm font-medium text-subtle mb-3">LLM Operations</h3>
        <p className="text-xs text-subtle">Unavailable</p>
      </div>
    );
  }

  return (
    <div data-testid="llm-operations-panel" className="rounded-xl bg-card border border-border p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium">LLM Operations</h3>
        <Button variant="secondary" size="sm" onClick={() => setDetailOpen(true)}>
          View Details
        </Button>
      </div>

      {/* Cost overview */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        <MetricCard
          label="Cost Today"
          value={`$${data.cost_today_usd.toFixed(2)}`}
          subtitle={costDelta(data.cost_today_usd, data.cost_yesterday_usd)}
        />
        <MetricCard
          label="Cascade Rate"
          value={`${data.cascade_rate_pct.toFixed(1)}%`}
          status={data.cascade_rate_pct > 20 ? "warn" : "ok"}
        />
      </div>

      {/* Tier health */}
      {data.tiers.length > 0 && (
        <div className="mb-4">
          <p className="text-xs text-subtle mb-2">Model Tiers</p>
          <div className="space-y-2">
            {data.tiers.map((tier) => (
              <div key={tier.model} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <StatusDot
                    status={tier.status === "ok" || tier.status === "healthy" ? "ok" : "degraded"}
                    size="sm"
                  />
                  <span className="font-mono">{tier.model}</span>
                </div>
                <span className="text-subtle">
                  {tier.latency?.avg_ms != null ? `${tier.latency.avg_ms.toFixed(0)}ms avg` : "N/A"}
                  {tier.failures_5m > 0 && (
                    <span className="ml-2 text-red-400">{tier.failures_5m} fail</span>
                  )}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Token budgets */}
      {data.token_budgets.length > 0 && (
        <div>
          <p className="text-xs text-subtle mb-2">Token Budgets</p>
          <div className="space-y-3">
            {data.token_budgets.map((budget) => (
              <div key={budget.model}>
                <GaugeBar
                  value={budget.tpm_used_pct}
                  label={`${budget.model} TPM`}
                />
              </div>
            ))}
          </div>
        </div>
      )}

      <DrillDownSheet
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        title="LLM Operations Details"
        onRefresh={() => refetch()}
        isRefreshing={isFetching}
      >
        {drillDown ? <LlmDetail data={drillDown} /> : <p className="text-xs text-subtle">Loading...</p>}
      </DrillDownSheet>
    </div>
  );
}
