import { cn } from "@/lib/utils";

interface SectorBar {
  sector: string;
  changePct: number;
}

interface SectorPerformanceBarsProps {
  sectors: SectorBar[];
  className?: string;
}

export function SectorPerformanceBars({ sectors, className }: SectorPerformanceBarsProps) {
  const maxAbs = Math.max(...sectors.map(s => Math.abs(s.changePct)), 1);

  return (
    <div className={cn("space-y-1.5", className)}>
      {sectors.map((s) => {
        const widthPct = Math.min((Math.abs(s.changePct) / maxAbs) * 100, 100);
        const isPositive = s.changePct >= 0;
        return (
          <div key={s.sector} className="flex items-center gap-2" aria-label={`${s.sector}: ${isPositive ? "+" : ""}${s.changePct.toFixed(2)}%`}>
            <span className="w-28 shrink-0 text-[11px] text-muted-foreground truncate">{s.sector}</span>
            <div className="relative flex-1 h-4 rounded bg-[rgba(15,23,42,0.5)]">
              <div
                className={cn(
                  "absolute inset-y-0 rounded",
                  isPositive ? "bg-[var(--gain)]/30 left-0" : "bg-[var(--loss)]/30 right-0",
                )}
                style={{ width: `${widthPct}%` }}
              />
            </div>
            <span className={cn(
              "w-14 text-right text-xs font-semibold",
              isPositive ? "text-[var(--gain)]" : "text-[var(--loss)]",
            )}>
              {isPositive ? "+" : ""}{s.changePct.toFixed(2)}%
            </span>
          </div>
        );
      })}
    </div>
  );
}
