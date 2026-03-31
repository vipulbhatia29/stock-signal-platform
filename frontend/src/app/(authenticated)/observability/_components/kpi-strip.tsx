"use client";

import { SectionHeading } from "@/components/section-heading";
import { StatTile } from "@/components/stat-tile";
import { Skeleton } from "@/components/ui/skeleton";
import { StaggerGroup, StaggerItem } from "@/components/motion-primitives";
import { useObservabilityKPIs } from "@/hooks/use-observability";
import { formatMicroCurrency, formatDuration, formatPercent } from "@/lib/format";

function passRateAccent(rate: number | null): "gain" | "warn" | "loss" | "cyan" {
  if (rate === null) return "cyan";
  if (rate >= 0.8) return "gain";
  if (rate >= 0.5) return "warn";
  return "loss";
}

function fallbackAccent(rate: number): "gain" | "warn" | "loss" {
  if (rate < 0.05) return "gain";
  if (rate < 0.15) return "warn";
  return "loss";
}

export function KPIStrip() {
  const { data, isLoading } = useObservabilityKPIs();

  return (
    <section aria-label="Key Metrics">
      <SectionHeading>AI Agent Metrics</SectionHeading>

      {isLoading || !data ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-[72px] w-full rounded-lg bg-card2" />
          ))}
        </div>
      ) : (
        <StaggerGroup stagger={0.06} className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          <StaggerItem>
            <StatTile label="Queries Today" value={String(data.queries_today)} accentColor="cyan" />
          </StaggerItem>
          <StaggerItem>
            <StatTile label="Avg Latency" value={formatDuration(data.avg_latency_ms)} accentColor="cyan" />
          </StaggerItem>
          <StaggerItem>
            <StatTile label="Avg Cost / Query" value={formatMicroCurrency(data.avg_cost_per_query)} accentColor="cyan" />
          </StaggerItem>
          <StaggerItem>
            <StatTile
              label="Pass Rate"
              value={data.pass_rate !== null ? formatPercent(data.pass_rate) : "—"}
              accentColor={passRateAccent(data.pass_rate)}
            />
          </StaggerItem>
          <StaggerItem>
            <StatTile
              label="Fallback Rate"
              value={formatPercent(data.fallback_rate_pct)}
              accentColor={fallbackAccent(data.fallback_rate_pct)}
            />
          </StaggerItem>
        </StaggerGroup>
      )}
    </section>
  );
}
