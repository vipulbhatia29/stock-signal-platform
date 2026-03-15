// AllocationDonut — CSS conic-gradient pie chart with legend.
// Used in the Dashboard Overview tiles row.

const DONUT_COLORS = [
  "#38bdf8", // cyan
  "#fbbf24", // warning/amber
  "#a78bfa", // purple
  "#22d3a0", // gain/teal
  "#f87171", // loss/red
  "#fb923c", // orange
] as const;

interface AllocationItem {
  sector: string;
  pct: number;
  color: string;
}

interface AllocationDonutProps {
  allocations: AllocationItem[];
  stockCount?: number;
}

export function buildGradient(allocations: AllocationItem[]): string {
  let cumulative = 0;
  const stops = allocations.map(({ pct, color }) => {
    const start = cumulative;
    cumulative += pct;
    return `${color} ${start.toFixed(1)}% ${cumulative.toFixed(1)}%`;
  });
  return `conic-gradient(${stops.join(", ")})`;
}

export function AllocationDonut({ allocations, stockCount }: AllocationDonutProps) {
  if (!allocations.length) {
    return (
      <div className="text-[10px] text-subtle mt-2">No positions</div>
    );
  }

  const gradient = buildGradient(allocations);
  const displayed = allocations.slice(0, 3);
  const remainder = allocations.length - 3;

  return (
    <div className="flex items-center gap-2.5 mt-2">
      {/* Donut */}
      <div
        className="w-[72px] h-[72px] rounded-full flex-shrink-0 flex items-center justify-center"
        style={{ background: gradient }}
      >
        <div className="w-[46px] h-[46px] rounded-full bg-card flex items-center justify-center">
          <div className="text-center leading-tight">
            <div className="font-mono text-[12px] font-bold text-foreground">
              {stockCount ?? allocations.length}
            </div>
            <div className="text-[8px] text-subtle">stocks</div>
          </div>
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-col gap-1 flex-1">
        {displayed.map((a) => (
          <div key={a.sector} className="flex items-center gap-1.5">
            <span
              className="w-1.5 h-1.5 rounded-full flex-shrink-0"
              style={{ background: a.color }}
            />
            <span className="text-[10px] text-muted-foreground flex-1 truncate">
              {a.sector}
            </span>
            <span className="font-mono text-[10px] text-subtle">
              {a.pct.toFixed(0)}%
            </span>
          </div>
        ))}
        {remainder > 0 && (
          <div className="text-[9px] text-subtle">+{remainder} more</div>
        )}
      </div>
    </div>
  );
}

export { DONUT_COLORS };
