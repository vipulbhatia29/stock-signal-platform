import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MetricCard } from "@/components/metric-card";
import { formatPercent, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ReturnsMetrics } from "@/types/api";

interface RiskReturnCardProps {
  returns: ReturnsMetrics | undefined;
}

export function RiskReturnCard({ returns }: RiskReturnCardProps) {
  if (!returns) return null;

  const metrics = [
    {
      label: "Annual Return",
      value: formatPercent(returns.annual_return),
      valueClassName:
        returns.annual_return !== null && returns.annual_return >= 0
          ? "text-gain"
          : "text-loss",
    },
    {
      label: "Volatility",
      value: formatPercent(returns.volatility),
      valueClassName: "text-foreground",
    },
    {
      label: "Sharpe Ratio",
      value: formatNumber(returns.sharpe),
      valueClassName:
        returns.sharpe !== null
          ? returns.sharpe > 1
            ? "text-gain"
            : returns.sharpe < 0
              ? "text-loss"
              : "text-foreground"
          : "text-foreground",
    },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground">
          Risk & Return
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
          {metrics.map((m) => (
            <MetricCard
              key={m.label}
              label={m.label}
              value={m.value}
              valueClassName={cn("text-xl font-semibold tabular-nums", m.valueClassName)}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
