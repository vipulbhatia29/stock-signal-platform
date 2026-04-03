"use client";

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
import { formatCurrency } from "@/lib/format";
import type { MonteCarloSummary } from "@/types/api";

interface MonteCarloChartProps {
  data: MonteCarloSummary | undefined;
  isLoading: boolean;
}

/** Monte Carlo simulation chart with percentile fan (p5/p25/p50/p75/p95). */
export function MonteCarloChart({ data, isLoading }: MonteCarloChartProps) {
  const colors = useChartColors();

  if (isLoading) {
    return (
      <div className="rounded-lg border border-border bg-card p-4 animate-pulse">
        <div className="h-4 w-40 rounded bg-border mb-3" />
        <div className="h-48 w-full rounded bg-border" />
      </div>
    );
  }

  if (!data || data.bands.p50.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
          No simulation data available.
        </div>
      </div>
    );
  }

  // Transform band arrays into chart-ready data points
  const chartData = data.bands.p50.map((_, i) => ({
    day: i,
    p5: data.bands.p5[i],
    p25: data.bands.p25[i],
    p50: data.bands.p50[i],
    p75: data.bands.p75[i],
    p95: data.bands.p95[i],
  }));

  return (
    <div className="relative rounded-lg border border-border bg-card p-4 overflow-hidden">
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-primary to-transparent" />
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-[9px] font-semibold uppercase tracking-[0.08em] text-subtle">
            Monte Carlo Simulation
          </div>
          <div className="text-xs text-muted-foreground">
            {data.simulation_days}-day horizon &middot;{" "}
            {formatCurrency(data.initial_value)} initial
          </div>
        </div>
        <div className="text-right">
          <div className="font-mono text-sm font-semibold text-foreground">
            {formatCurrency(data.terminal_median)}
          </div>
          <div className="text-[10px] text-subtle">median outcome</div>
        </div>
      </div>

      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={chartData}
            margin={{ top: 4, right: 4, bottom: 0, left: 0 }}
          >
            <CartesianGrid
              strokeDasharray={CHART_STYLE.grid.strokeDasharray}
              className={CHART_STYLE.grid.className}
              vertical={false}
            />
            <XAxis
              dataKey="day"
              tick={{ fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              className={CHART_STYLE.axis.className}
              tickFormatter={(d: number) => `${d}d`}
            />
            <YAxis
              tick={{ fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              className={CHART_STYLE.axis.className}
              tickFormatter={(v: number) =>
                `$${(v / 1000).toFixed(0)}k`
              }
              width={50}
            />
            <Tooltip
              formatter={(v) => formatCurrency(Number(v))}
              labelFormatter={(d) => `Day ${d}`}
              contentStyle={{
                background: "var(--card2)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius)",
              }}
            />
            {/* Outer band: p5-p95 */}
            <Area
              type="monotone"
              dataKey="p95"
              stroke="none"
              fill={colors.chart1}
              fillOpacity={0.08}
              isAnimationActive={false}
            />
            <Area
              type="monotone"
              dataKey="p5"
              stroke="none"
              fill="var(--card)"
              fillOpacity={1}
              isAnimationActive={false}
            />
            {/* Inner band: p25-p75 */}
            <Area
              type="monotone"
              dataKey="p75"
              stroke="none"
              fill={colors.chart1}
              fillOpacity={0.15}
              isAnimationActive={false}
            />
            <Area
              type="monotone"
              dataKey="p25"
              stroke="none"
              fill="var(--card)"
              fillOpacity={1}
              isAnimationActive={false}
            />
            {/* Median line */}
            <Area
              type="monotone"
              dataKey="p50"
              stroke={colors.chart1}
              strokeWidth={2}
              fill="none"
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Terminal values summary */}
      <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
        <span>
          Worst 5%: <span className="text-loss font-mono">{formatCurrency(data.terminal_p5)}</span>
        </span>
        <span>
          Best 5%: <span className="text-gain font-mono">{formatCurrency(data.terminal_p95)}</span>
        </span>
      </div>
    </div>
  );
}
