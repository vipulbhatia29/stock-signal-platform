import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
      color:
        returns.annual_return !== null && returns.annual_return >= 0
          ? "text-gain"
          : "text-loss",
    },
    {
      label: "Volatility",
      value: formatPercent(returns.volatility),
      color: "text-foreground",
    },
    {
      label: "Sharpe Ratio",
      value: formatNumber(returns.sharpe),
      color:
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
            <div key={m.label}>
              <p className="text-xs uppercase tracking-wider text-muted-foreground">
                {m.label}
              </p>
              <p
                className={cn(
                  "mt-1 text-xl font-semibold tabular-nums",
                  m.color
                )}
              >
                {m.value}
              </p>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
