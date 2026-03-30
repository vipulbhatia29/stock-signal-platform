"use client";

import { Bell } from "lucide-react";
import { SectionHeading } from "@/components/section-heading";
import { AlertTile } from "@/components/alert-tile";
import { EmptyState } from "@/components/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useAlerts } from "@/hooks/use-alerts";
import { formatRelativeTime } from "@/lib/format";

/** Map backend severity to AlertTile severity. */
function mapSeverity(sev: string): "critical" | "high" | "medium" | "low" {
  if (sev === "critical") return "critical";
  if (sev === "warning") return "high";
  if (sev === "info") return "medium";
  return "low";
}

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
          {unreadCount > 0 && (
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
        <EmptyState icon={Bell} title="No alerts" description="You're all clear — no alerts at this time" />
      ) : (
        <div className="space-y-2">
          {recentAlerts.map((alert) => (
            <AlertTile
              key={alert.id}
              title={alert.title}
              ticker={alert.ticker ?? undefined}
              severity={mapSeverity(alert.severity)}
              message={alert.message}
              timestamp={formatRelativeTime(alert.created_at)}
            />
          ))}
        </div>
      )}
    </section>
  );
}
