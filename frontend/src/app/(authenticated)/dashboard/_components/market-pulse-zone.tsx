"use client";

import { Activity, Clock } from "lucide-react";
import { SectionHeading } from "@/components/section-heading";
import { IndexCard, IndexCardSkeleton } from "@/components/index-card";
import { useIndexes } from "@/hooks/use-stocks";
import { cn } from "@/lib/utils";

/** Zone 1 — Market status indicator + index performance cards. */
export function MarketPulseZone() {
  const { data: indexes, isLoading, isError } = useIndexes();

  // Simple market-open check: NYSE hours 9:30-16:00 ET, weekdays
  const now = new Date();
  const et = new Date(
    now.toLocaleString("en-US", { timeZone: "America/New_York" })
  );
  const day = et.getDay();
  const hour = et.getHours();
  const minute = et.getMinutes();
  const minuteOfDay = hour * 60 + minute;
  const isOpen =
    day >= 1 && day <= 5 && minuteOfDay >= 570 && minuteOfDay < 960;

  return (
    <section aria-label="Market Pulse">
      <SectionHeading
        action={
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-semibold",
              isOpen
                ? "bg-gain/10 text-gain"
                : "bg-muted text-muted-foreground"
            )}
            aria-label={isOpen ? "US stock market is currently open" : "US stock market is currently closed"}
          >
            {isOpen ? (
              <Activity className="h-3 w-3 animate-pulse" aria-hidden="true" />
            ) : (
              <Clock className="h-3 w-3" aria-hidden="true" />
            )}
            {isOpen ? "Market Open" : "Market Closed"}
          </span>
        }
      >
        Market Pulse
      </SectionHeading>

      {isError ? (
        <p className="text-sm text-muted-foreground">
          Unable to load market data.
        </p>
      ) : isLoading ? (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <IndexCardSkeleton key={i} />
          ))}
        </div>
      ) : !indexes?.length ? (
        <p className="text-sm text-muted-foreground">
          No index data available yet.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {indexes.map((idx, i) => (
            <IndexCard
              key={idx.slug}
              name={idx.name}
              slug={idx.slug}
              stockCount={idx.stock_count}
              description={idx.description}
              animationDelay={i * 80}
            />
          ))}
        </div>
      )}
    </section>
  );
}
