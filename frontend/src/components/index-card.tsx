import Link from "next/link";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface IndexCardProps {
  name: string;
  slug: string;
  stockCount: number;
  description: string | null;
  animationDelay?: number;
}

export function IndexCard({
  name,
  slug,
  stockCount,
  description,
  animationDelay = 0,
}: IndexCardProps) {
  return (
    <Link href={`/screener?index=${slug}`}>
      <div
        className={cn(
          "relative overflow-hidden rounded-[var(--radius)] border border-border bg-card p-[11px_13px_9px]",
          "cursor-pointer transition-colors hover:border-[var(--bhi)] hover:bg-hov animate-fade-slide-up"
        )}
        style={{ "--stagger-delay": `${animationDelay}ms` } as React.CSSProperties}
      >
        {/* Top accent line */}
        <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-cyan to-transparent" />

        <div className="flex items-baseline justify-between mb-1">
          <span className="text-[10px] font-semibold uppercase tracking-[0.07em] text-muted-foreground">
            {name}
          </span>
          {description && (
            <span className="text-[10px] text-subtle truncate max-w-[120px]">
              {description}
            </span>
          )}
        </div>

        <div className="font-mono text-[17px] font-semibold tracking-tight text-foreground">
          {stockCount}
          <span className="text-[11px] font-normal text-subtle ml-1">stocks</span>
        </div>
      </div>
    </Link>
  );
}

export function IndexCardSkeleton() {
  return (
    <div className="rounded-[var(--radius)] border border-border bg-card p-[11px_13px_9px]">
      <Skeleton className="h-3 w-24 mb-2 bg-card2" />
      <Skeleton className="h-5 w-16 bg-card2" />
    </div>
  );
}
