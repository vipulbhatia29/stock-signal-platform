import type { SectorAllocation } from "@/lib/mock-data";

interface AllocationDonutProps {
  sectors: SectorAllocation[];
  size?: number;
  holeRatio?: number;
}

function buildConicGradient(sectors: SectorAllocation[]): string {
  let cum = 0;
  const stops = sectors.map((s) => {
    const start = cum;
    cum += s.pct;
    return `${s.color} ${start}% ${cum}%`;
  });
  return `conic-gradient(from -90deg, ${stops.join(", ")})`;
}

export function AllocationDonut({ sectors, size = 80, holeRatio = 0.6 }: AllocationDonutProps) {
  const hole = size * holeRatio;
  const inset = (size - hole) / 2;

  return (
    <div className="flex items-center gap-4">
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <div className="h-full w-full rounded-full" style={{ background: buildConicGradient(sectors) }} />
        <div className="absolute rounded-full bg-card" style={{ inset }} />
      </div>
      <div className="flex flex-col gap-1 min-w-0">
        {sectors.map((s) => (
          <div key={s.sector} className="flex items-center gap-2 text-[10px]">
            <span className="h-1.5 w-1.5 shrink-0 rounded-sm" style={{ backgroundColor: s.color }} />
            <span className="truncate text-muted-foreground">{s.sector}</span>
            <span className="ml-auto font-mono text-foreground">{s.pct}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}
