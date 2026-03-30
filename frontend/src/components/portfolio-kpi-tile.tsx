import { cn } from "@/lib/utils";

interface PortfolioKPITileProps {
  label: string;
  value: string;
  subtext?: string;
  accent?: "gain" | "loss" | "neutral";
  className?: string;
}

export function PortfolioKPITile({ label, value, subtext, accent = "neutral", className }: PortfolioKPITileProps) {
  return (
    <div className={cn(
      "rounded-lg border border-border/30 bg-[rgba(15,23,42,0.5)] p-3",
      accent === "gain" && "border-t-2 border-t-[var(--gain)]",
      accent === "loss" && "border-t-2 border-t-[var(--loss)]",
      accent === "neutral" && "border-t-2 border-t-muted-foreground/40",
      className,
    )}>
      <div className="text-[11px] font-medium text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-lg font-bold text-foreground">{value}</div>
      {subtext && <div className="text-[10px] text-muted-foreground">{subtext}</div>}
    </div>
  );
}
