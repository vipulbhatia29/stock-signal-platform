import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Sparkline } from "@/components/sparkline";
import { ChangeIndicator } from "@/components/change-indicator";
import { cn } from "@/lib/utils";

interface IndexCardProps {
  name: string;
  slug: string;
  stockCount: number;
  description: string | null;
  value?: number;
  changePct?: number;
  sparklineData?: number[];
  animationDelay?: number;
}

export function IndexCard({
  name,
  slug,
  stockCount,
  value,
  changePct,
  sparklineData,
  animationDelay = 0,
}: IndexCardProps) {
  return (
    <Link href={`/screener?index=${slug}`}>
      <div
        className={cn(
          "relative overflow-hidden rounded-[var(--radius)] border border-border bg-card p-3",
          "cursor-pointer transition-colors hover:border-[var(--bhi)] hover:bg-hov animate-fade-slide-up",
          "flex items-center justify-between gap-3"
        )}
        style={{ "--stagger-delay": `${animationDelay}ms` } as React.CSSProperties}
      >
        <div className="flex-1 min-w-0">
          <div className="text-xs font-semibold text-foreground mb-0.5">
            {name}
          </div>
          <div className="flex items-center gap-2">
            {value != null && (
              <span className="font-mono text-sm font-semibold text-foreground tabular-nums">
                {value.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}
              </span>
            )}
            {changePct != null && (
              <ChangeIndicator value={changePct} size="sm" showIcon={false} />
            )}
          </div>
          <div className="text-[10px] text-muted-foreground mt-0.5">
            {stockCount} stocks
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {sparklineData && sparklineData.length > 0 && (
            <Sparkline data={sparklineData} width={64} height={28} />
          )}
          <ChevronRight size={14} className="text-subtle" />
        </div>
      </div>
    </Link>
  );
}

export function IndexCardSkeleton() {
  return (
    <div className="rounded-[var(--radius)] border border-border bg-card p-3">
      <Skeleton className="h-3 w-24 mb-2 bg-card2" />
      <Skeleton className="h-5 w-16 bg-card2" />
    </div>
  );
}
