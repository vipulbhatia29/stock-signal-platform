// ChartTooltip — reusable Recharts custom tooltip.
// Replaces duplicated inline tooltip render functions in price-chart and signal-history-chart.

interface TooltipItem {
  name: string;
  value: string;
  color?: string;
}

interface ChartTooltipProps {
  active?: boolean;
  label: string;
  items: TooltipItem[];
}

export function ChartTooltip({ active, label, items }: ChartTooltipProps) {
  if (!active || !items.length) return null;

  return (
    <div className="rounded-lg border bg-popover px-3 py-2 text-sm shadow-md">
      <p className="mb-1.5 font-medium">{label}</p>
      {items.map((item) => (
        <div key={item.name} className="flex items-center gap-2">
          {item.color && (
            <span
              className="inline-block size-2 shrink-0 rounded-full"
              style={{ backgroundColor: item.color }}
              aria-hidden="true"
            />
          )}
          <span className="text-muted-foreground">{item.name}:</span>
          <span className="tabular-nums">{item.value}</span>
        </div>
      ))}
    </div>
  );
}
