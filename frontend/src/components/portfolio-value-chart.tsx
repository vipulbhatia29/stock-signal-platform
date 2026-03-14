"use client";

// Portfolio value history chart — shows daily total value + cost basis over time.
// Data comes from the PortfolioSnapshot hypertable (Celery daily snapshots).

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { useChartColors, CHART_STYLE } from "@/lib/chart-theme";
import { ChartTooltip } from "@/components/chart-tooltip";
import { formatCurrency, formatChartDate } from "@/lib/format";
import type { PortfolioSnapshot } from "@/types/api";

interface PortfolioValueChartProps {
  snapshots: PortfolioSnapshot[];
}

export function PortfolioValueChart({ snapshots }: PortfolioValueChartProps) {
  const colors = useChartColors();

  if (snapshots.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
        No history yet. Snapshots are captured daily at market close.
      </div>
    );
  }

  const data = snapshots.map((s) => ({
    date: s.snapshot_date,
    value: s.total_value,
    costBasis: s.total_cost_basis,
    pnl: s.unrealized_pnl,
  }));

  // Determine if overall trend is positive for color
  const first = data[0];
  const last = data[data.length - 1];
  const trending = last.value >= first.value;
  const areaColor = trending ? colors.gain : colors.loss;

  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="valueGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={areaColor} stopOpacity={0.3} />
            <stop offset="95%" stopColor={areaColor} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid {...CHART_STYLE.grid} />
        <XAxis
          dataKey="date"
          tickFormatter={(d) => formatChartDate(d)}
          {...CHART_STYLE.axis}
        />
        <YAxis
          tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
          width={60}
          {...CHART_STYLE.axis}
        />
        <Tooltip
          content={({ active, payload, label }) => (
            <ChartTooltip
              active={active}
              label={formatChartDate(label as string)}
              items={
                payload?.map((p) => ({
                  name: p.dataKey === "value" ? "Value" : "Cost Basis",
                  value: formatCurrency(
                    typeof p.value === "number" ? p.value : null
                  ),
                  color: p.dataKey === "value" ? areaColor : colors.chart2,
                })) ?? []
              }
            />
          )}
          {...CHART_STYLE.tooltip}
        />
        <Area
          type="monotone"
          dataKey="costBasis"
          stroke={colors.chart2}
          strokeWidth={1}
          strokeDasharray="4 2"
          fill="none"
          dot={false}
        />
        <Area
          type="monotone"
          dataKey="value"
          stroke={areaColor}
          strokeWidth={2}
          fill="url(#valueGradient)"
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
