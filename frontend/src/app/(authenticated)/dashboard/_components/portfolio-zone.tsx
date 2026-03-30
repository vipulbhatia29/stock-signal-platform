"use client";

import { useMemo, useState } from "react";
import { Briefcase } from "lucide-react";
import { SectionHeading } from "@/components/section-heading";
import { StatTile } from "@/components/stat-tile";
import { ChangeIndicator } from "@/components/change-indicator";
import { AllocationDonut, DONUT_COLORS } from "@/components/allocation-donut";
import { PortfolioDrawer } from "@/components/portfolio-drawer";
import { EmptyState } from "@/components/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { usePortfolioSummary, usePositions } from "@/hooks/use-stocks";
import { formatCurrency } from "@/lib/format";
import { StaggerGroup, StaggerItem } from "@/components/motion-primitives";

/** Zone 3 — Portfolio KPIs, allocation, and health overview. */
export function PortfolioZone() {
  const { data: summary, isLoading: summaryLoading } = usePortfolioSummary();
  const { data: positions, isLoading: positionsLoading } = usePositions();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const isLoading = summaryLoading || positionsLoading;

  const allocations = useMemo(() => {
    if (!positions) return [];
    const sectorTotals: Record<string, number> = {};
    let total = 0;
    positions.forEach((p) => {
      const sector = p.sector ?? "Other";
      sectorTotals[sector] =
        (sectorTotals[sector] ?? 0) + (p.market_value ?? 0);
      total += p.market_value ?? 0;
    });
    return Object.entries(sectorTotals).map(([sector, value], i) => ({
      sector,
      pct: total > 0 ? (value / total) * 100 : 0,
      color: DONUT_COLORS[i % DONUT_COLORS.length],
    }));
  }, [positions]);

  // Sector performance bars from allocation data
  const sectorBars = useMemo(() => {
    if (!summary?.sectors) return [];
    return summary.sectors
      .sort((a, b) => b.pct - a.pct)
      .slice(0, 6)
      .map((s) => ({
        sector: s.sector,
        pct: s.pct,
        overLimit: s.over_limit,
      }));
  }, [summary]);

  if (isLoading) {
    return (
      <section>
        <SectionHeading>Portfolio Overview</SectionHeading>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20 rounded-lg bg-card2" />
          ))}
        </div>
      </section>
    );
  }

  if (!positions?.length) {
    return (
      <section>
        <SectionHeading>Portfolio Overview</SectionHeading>
        <EmptyState
          icon={Briefcase}
          title="No portfolio yet"
          description="Log your first transaction to see portfolio analytics here"
        />
      </section>
    );
  }

  return (
    <section>
      <SectionHeading>Portfolio Overview</SectionHeading>

      <StaggerGroup className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {/* Total Value */}
        <StaggerItem>
          <StatTile
            label="Total Value"
            value={summary ? formatCurrency(summary.total_value) : "—"}
            sub={
              <span className="text-[9px] text-subtle">
                {summary?.position_count ?? 0} positions
              </span>
            }
            accentColor="cyan"
            onClick={() => setDrawerOpen(true)}
          />
        </StaggerItem>

        {/* Unrealized P&L */}
        <StaggerItem>
          <StatTile
            label="Unrealized P&L"
            value={summary ? formatCurrency(summary.unrealized_pnl) : "—"}
            sub={
              summary?.unrealized_pnl_pct != null ? (
                <ChangeIndicator
                  value={summary.unrealized_pnl_pct}
                  format="percent"
                  size="sm"
                  showIcon={false}
                />
              ) : undefined
            }
            accentColor={
              (summary?.unrealized_pnl ?? 0) >= 0 ? "gain" : "loss"
            }
          />
        </StaggerItem>

        {/* Cost Basis */}
        <StaggerItem>
          <StatTile
            label="Cost Basis"
            value={summary ? formatCurrency(summary.total_cost_basis) : "—"}
            accentColor="cyan"
          />
        </StaggerItem>

        {/* Sector Allocation */}
        <StaggerItem>
          <StatTile label="Allocation" accentColor="cyan">
            <AllocationDonut
              allocations={allocations}
              stockCount={positions?.length}
              showSectorLink
            />
          </StatTile>
        </StaggerItem>
      </StaggerGroup>

      {/* Sector bars */}
      {sectorBars.length > 0 && (
        <div className="mt-3 rounded-lg border border-border bg-card p-3">
          <div className="mb-2 text-[9px] font-semibold uppercase tracking-wider text-subtle">
            Sector Allocation
          </div>
          <div className="space-y-1.5">
            {sectorBars.map((s) => (
              <div key={s.sector} className="flex items-center gap-2">
                <span className="w-28 truncate text-[10px] text-muted-foreground">
                  {s.sector}
                </span>
                <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                  <div
                    className={`h-full rounded-full ${s.overLimit ? "bg-loss" : "bg-cyan"}`}
                    style={{ width: `${Math.min(s.pct, 100)}%` }}
                  />
                </div>
                <span className="w-10 text-right font-mono text-[10px] text-muted-foreground">
                  {s.pct.toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <PortfolioDrawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      />
    </section>
  );
}
