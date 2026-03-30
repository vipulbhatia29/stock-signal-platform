"use client";

import { Bell, AlertTriangle, Info } from "lucide-react";
import { SectionHeading } from "@/components/section-heading";
import { EmptyState } from "@/components/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useAlerts } from "@/hooks/use-alerts";
import { cn } from "@/lib/utils";
import { formatRelativeTime } from "@/lib/format";
import Link from "next/link";

const SEVERITY_STYLES: Record<string, { bg: string; text: string; icon: typeof AlertTriangle }> = {
  critical: { bg: "bg-loss/10", text: "text-loss", icon: AlertTriangle },
  warning: { bg: "bg-warning/10", text: "text-warning", icon: AlertTriangle },
  info: { bg: "bg-cyan/10", text: "text-cyan", icon: Info },
};

/** Zone 4 — Recent alerts grid. */
export function AlertsZone() {
  const { data, isLoading, isError } = useAlerts();

  const recentAlerts = data?.alerts?.slice(0, 6) ?? [];
  const unreadCount = data?.unreadCount ?? 0;

  if (isError) {
    return (
      <section aria-label="Alerts">
        <SectionHeading>Alerts</SectionHeading>
        <p className="text-sm text-muted-foreground">Unable to load alerts.</p>
      </section>
    );
  }

  return (
    <section aria-label="Alerts">
      <SectionHeading>
        <span className="inline-flex items-center gap-1.5">
          <Bell className="h-3 w-3" />
          Alerts
          {recentAlerts.length > 0 && (
            <span className="ml-1 rounded-full bg-loss/10 px-1.5 py-0.5 text-[9px] font-bold text-loss">
              {unreadCount}
            </span>
          )}
        </span>
      </SectionHeading>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full rounded-lg bg-card2" />
          ))}
        </div>
      ) : recentAlerts.length === 0 ? (
        <EmptyState
          icon={Bell}
          title="No alerts"
          description="You're all clear — no alerts at this time"
        />
      ) : (
        <div className="space-y-2">
          {recentAlerts.map((alert) => {
            const style =
              SEVERITY_STYLES[alert.severity] ?? SEVERITY_STYLES.info;
            const Icon = style.icon;

            return (
              <div
                key={alert.id}
                className={cn(
                  "flex items-start gap-3 rounded-lg border border-border bg-card px-3 py-2.5",
                  !alert.is_read && "border-l-2 border-l-warning"
                )}
              >
                <div
                  className={cn(
                    "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded",
                    style.bg
                  )}
                >
                  <Icon className={cn("h-3.5 w-3.5", style.text)} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold text-foreground">
                      {alert.title}
                    </span>
                    <span className="shrink-0 text-[9px] text-muted-foreground">
                      {formatRelativeTime(alert.created_at)}
                    </span>
                  </div>
                  <p className="mt-0.5 text-[10px] text-muted-foreground line-clamp-2">
                    {alert.message}
                  </p>
                  {alert.ticker && (
                    <Link
                      href={`/stocks/${alert.ticker}`}
                      className="mt-1 inline-block font-mono text-[10px] font-semibold text-cyan hover:underline"
                    >
                      {alert.ticker}
                    </Link>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
