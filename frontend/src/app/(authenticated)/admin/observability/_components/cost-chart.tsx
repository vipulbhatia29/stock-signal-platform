"use client";

import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import { CHART_STYLE, useChartColors } from "@/lib/chart-theme";
import type { CostGroup } from "@/types/admin-observability";

interface CostChartProps {
  groups: CostGroup[];
  dimensionKey: string;
}

export function CostChart({ groups, dimensionKey }: CostChartProps) {
  const colors = useChartColors();

  const chartData = groups.slice(0, 10).map((g) => ({
    label: String(g[dimensionKey] ?? "unknown"),
    cost: g.total_cost_usd ?? 0,
    calls: g.call_count,
  }));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={chartData} layout="horizontal">
        <CartesianGrid {...CHART_STYLE.grid} />
        <XAxis
          dataKey="label"
          {...CHART_STYLE.axis}
          tick={{ fontSize: 10 }}
        />
        <YAxis
          tickFormatter={(v: number) => `$${v.toFixed(3)}`}
          {...CHART_STYLE.axis}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "var(--card)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius)",
          }}
          labelStyle={{ color: "var(--foreground)" }}
          formatter={(value) => [`$${Number(value ?? 0).toFixed(4)}`, "Cost"]}
          isAnimationActive={false}
        />
        <Bar
          dataKey="cost"
          fill={colors.chart1 || colors.price}
          name="Cost (USD)"
          radius={[4, 4, 0, 0]}
          isAnimationActive={false}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
