"use client";

import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  ReferenceLine,
  Legend,
} from "recharts";
import { useSignalHistory } from "@/hooks/use-stocks";
import { Skeleton } from "@/components/ui/skeleton";
import { ChartTooltip } from "@/components/chart-tooltip";
import { useChartColors, CHART_STYLE } from "@/lib/chart-theme";
import { formatChartDate, formatNumber } from "@/lib/format";

interface SignalHistoryChartProps {
  ticker: string;
}

export function SignalHistoryChart({ ticker }: SignalHistoryChartProps) {
  const { data: history, isLoading } = useSignalHistory(ticker, 90);
  const colors = useChartColors();

  if (isLoading) {
    return <Skeleton className="h-[200px] w-full sm:h-[300px]" />;
  }

  if (!history || history.length === 0) {
    return (
      <div className="flex h-[200px] items-center justify-center text-sm text-muted-foreground sm:h-[300px]">
        No signal history available
      </div>
    );
  }

  return (
    <ResponsiveContainer
      width="100%"
      height="100%"
      minHeight={200}
      className="sm:min-h-[300px]"
    >
      <ComposedChart
        data={history}
        role="img"
        aria-label={`${ticker} signal history chart`}
      >
        <CartesianGrid {...CHART_STYLE.grid} />
        <XAxis
          dataKey="computed_at"
          tickFormatter={formatChartDate}
          {...CHART_STYLE.axis}
        />
        <YAxis
          yAxisId="score"
          orientation="left"
          domain={[0, 10]}
          width={35}
          label={{
            value: "Score",
            angle: -90,
            position: "insideLeft",
            style: { fontSize: 11 },
          }}
          {...CHART_STYLE.axis}
        />
        <YAxis
          yAxisId="rsi"
          orientation="right"
          domain={[0, 100]}
          width={35}
          label={{
            value: "RSI",
            angle: 90,
            position: "insideRight",
            style: { fontSize: 11 },
          }}
          {...CHART_STYLE.axis}
        />
        <Tooltip
          cursor={CHART_STYLE.tooltip.cursor}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0].payload as {
              computed_at: string;
              composite_score: number | null;
              rsi_value: number | null;
            };
            return (
              <ChartTooltip
                active={active}
                label={formatChartDate(d.computed_at)}
                items={[
                  { name: "Score", value: formatNumber(d.composite_score, 1), color: colors.chart1 },
                  { name: "RSI", value: formatNumber(d.rsi_value, 1), color: colors.chart2 },
                ]}
              />
            );
          }}
        />
        <Legend />
        <ReferenceLine
          yAxisId="rsi"
          y={70}
          stroke={colors.rsi}
          strokeDasharray="3 3"
          strokeOpacity={0.6}
        />
        <ReferenceLine
          yAxisId="rsi"
          y={30}
          stroke={colors.chart1}
          strokeDasharray="3 3"
          strokeOpacity={0.6}
        />
        <Line
          yAxisId="score"
          type="monotone"
          dataKey="composite_score"
          stroke={colors.chart1}
          strokeWidth={2}
          dot={false}
          name="Composite Score"
        />
        <Line
          yAxisId="rsi"
          type="monotone"
          dataKey="rsi_value"
          stroke={colors.chart2}
          strokeWidth={1.5}
          strokeDasharray="4 2"
          dot={false}
          name="RSI"
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
