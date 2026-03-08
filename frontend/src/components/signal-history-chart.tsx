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
import { formatChartDate, formatNumber } from "@/lib/format";

interface SignalHistoryChartProps {
  ticker: string;
}

export function SignalHistoryChart({ ticker }: SignalHistoryChartProps) {
  const { data: history, isLoading } = useSignalHistory(ticker, 90);

  if (isLoading) {
    return <Skeleton className="h-[300px] w-full" />;
  }

  if (!history || history.length === 0) {
    return (
      <div className="flex h-[300px] items-center justify-center text-sm text-muted-foreground">
        No signal history available
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <ComposedChart data={history}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-border/50" />
        <XAxis
          dataKey="computed_at"
          tickFormatter={formatChartDate}
          tick={{ fontSize: 11 }}
        />
        <YAxis
          yAxisId="score"
          orientation="left"
          domain={[0, 10]}
          tick={{ fontSize: 11 }}
          width={35}
          label={{
            value: "Score",
            angle: -90,
            position: "insideLeft",
            style: { fontSize: 11 },
          }}
        />
        <YAxis
          yAxisId="rsi"
          orientation="right"
          domain={[0, 100]}
          tick={{ fontSize: 11 }}
          width={35}
          label={{
            value: "RSI",
            angle: 90,
            position: "insideRight",
            style: { fontSize: 11 },
          }}
        />
        <Tooltip
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0].payload as {
              computed_at: string;
              composite_score: number | null;
              rsi_value: number | null;
            };
            return (
              <div className="rounded-lg border bg-popover px-3 py-2 text-sm shadow-md">
                <p className="font-medium">{formatChartDate(d.computed_at)}</p>
                <p style={{ color: "hsl(var(--chart-1))" }}>
                  Score: {formatNumber(d.composite_score, 1)}
                </p>
                <p style={{ color: "hsl(var(--chart-2))" }}>
                  RSI: {formatNumber(d.rsi_value, 1)}
                </p>
              </div>
            );
          }}
        />
        <Legend />
        <ReferenceLine
          yAxisId="rsi"
          y={70}
          stroke="hsl(var(--destructive))"
          strokeDasharray="3 3"
          strokeOpacity={0.5}
        />
        <ReferenceLine
          yAxisId="rsi"
          y={30}
          stroke="hsl(var(--chart-1))"
          strokeDasharray="3 3"
          strokeOpacity={0.5}
        />
        <Line
          yAxisId="score"
          type="monotone"
          dataKey="composite_score"
          stroke="hsl(var(--chart-1))"
          strokeWidth={2}
          dot={false}
          name="Composite Score"
        />
        <Line
          yAxisId="rsi"
          type="monotone"
          dataKey="rsi_value"
          stroke="hsl(var(--chart-2))"
          strokeWidth={1.5}
          strokeDasharray="4 2"
          dot={false}
          name="RSI"
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
