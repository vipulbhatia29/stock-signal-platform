"use client";

import {
  ComposedChart,
  Area,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { usePrices } from "@/hooks/use-stocks";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCurrency, formatVolume, formatChartDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { PricePeriod } from "@/types/api";

const PERIODS: { value: PricePeriod; label: string }[] = [
  { value: "1mo", label: "1M" },
  { value: "3mo", label: "3M" },
  { value: "6mo", label: "6M" },
  { value: "1y", label: "1Y" },
  { value: "5y", label: "5Y" },
];

interface PriceChartProps {
  ticker: string;
  period: PricePeriod;
  onPeriodChange: (p: PricePeriod) => void;
}

export function PriceChart({
  ticker,
  period,
  onPeriodChange,
}: PriceChartProps) {
  const { data: prices, isLoading } = usePrices(ticker, period);

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium uppercase tracking-wider text-muted-foreground">
          Price History
        </h2>
        <div className="flex gap-1">
          {PERIODS.map((p) => (
            <Button
              key={p.value}
              variant={period === p.value ? "secondary" : "ghost"}
              size="sm"
              className={cn("h-7 px-2.5 text-xs")}
              onClick={() => onPeriodChange(p.value)}
            >
              {p.label}
            </Button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <Skeleton className="h-[400px] w-full" />
      ) : (
        <ResponsiveContainer width="100%" height={400}>
          <ComposedChart data={prices}>
            <defs>
              <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
                <stop
                  offset="5%"
                  stopColor="hsl(var(--chart-1))"
                  stopOpacity={0.3}
                />
                <stop
                  offset="95%"
                  stopColor="hsl(var(--chart-1))"
                  stopOpacity={0}
                />
              </linearGradient>
            </defs>
            <CartesianGrid
              strokeDasharray="3 3"
              className="stroke-border/50"
            />
            <XAxis
              dataKey="time"
              tickFormatter={formatChartDate}
              tick={{ fontSize: 11 }}
              className="text-muted-foreground"
            />
            <YAxis
              yAxisId="price"
              orientation="left"
              tickFormatter={(v: number) => `$${v.toFixed(0)}`}
              tick={{ fontSize: 11 }}
              width={60}
            />
            <YAxis
              yAxisId="volume"
              orientation="right"
              tickFormatter={formatVolume}
              tick={{ fontSize: 11 }}
              width={50}
            />
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const d = payload[0].payload as {
                  time: string;
                  close: number;
                  volume: number;
                };
                return (
                  <div className="rounded-lg border bg-popover px-3 py-2 text-sm shadow-md">
                    <p className="font-medium">{formatChartDate(d.time)}</p>
                    <p className="text-muted-foreground">
                      Price: {formatCurrency(d.close)}
                    </p>
                    <p className="text-muted-foreground">
                      Volume: {formatVolume(d.volume)}
                    </p>
                  </div>
                );
              }}
            />
            <Area
              yAxisId="price"
              type="monotone"
              dataKey="close"
              stroke="hsl(var(--chart-1))"
              fill="url(#priceGradient)"
              strokeWidth={2}
            />
            <Bar
              yAxisId="volume"
              dataKey="volume"
              fill="hsl(var(--chart-3))"
              opacity={0.3}
            />
          </ComposedChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
