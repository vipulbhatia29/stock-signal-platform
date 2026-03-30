"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { Bell } from "lucide-react";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAlerts, useMarkAlertsRead } from "@/hooks/use-alerts";
import {
  Popover,
  PopoverTrigger,
  PopoverContent,
} from "@/components/ui/popover";
import type { AlertResponse } from "@/types/api";

const SEVERITY_COLORS: Record<string, string> = {
  critical: "text-loss",
  warning: "text-warning",
  info: "text-cyan",
};

function formatTimeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function formatTitle(alert: AlertResponse): string {
  if (alert.title) return alert.title;
  return alert.alert_type
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function AlertSkeleton() {
  return (
    <div className="space-y-3 p-4">
      {[1, 2, 3].map((i) => (
        <div key={i} className="flex gap-3 animate-pulse">
          <div className="w-2 h-2 rounded-full bg-muted mt-2 shrink-0" />
          <div className="flex-1 space-y-2">
            <div className="h-3 bg-muted rounded w-2/3" />
            <div className="h-3 bg-muted rounded w-full" />
          </div>
        </div>
      ))}
    </div>
  );
}

function AlertItem({
  alert,
  onClick,
}: {
  alert: AlertResponse;
  onClick: (alert: AlertResponse) => void;
}) {
  const severity = alert.severity as keyof typeof SEVERITY_COLORS;
  const color = SEVERITY_COLORS[severity] ?? "text-subtle";
  const title = formatTitle(alert);

  return (
    <button
      onClick={() => onClick(alert)}
      className={cn(
        "flex gap-3 px-4 py-3 w-full text-left border-b border-border/50",
        "hover:bg-muted/30 transition-colors",
        alert.is_read && "opacity-60",
      )}
    >
      <div className="flex-shrink-0 mt-1.5">
        {alert.is_read ? (
          <div className="w-2 h-2 rounded-full border border-muted-foreground/30" />
        ) : (
          <div className="w-2 h-2 rounded-full bg-blue-500" />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex justify-between items-baseline gap-2">
          <span className={cn("font-semibold text-xs", color)}>{title}</span>
          <span className="text-muted-foreground text-[11px] whitespace-nowrap">
            {formatTimeAgo(alert.created_at)}
          </span>
        </div>
        <p className="text-muted-foreground text-xs mt-0.5 line-clamp-2">
          {alert.message}
        </p>
        {alert.ticker && (
          <span className="text-muted-foreground text-[11px] bg-muted/50 px-2 py-0.5 rounded mt-1.5 inline-block">
            {alert.ticker} →
          </span>
        )}
      </div>
    </button>
  );
}

export function AlertBell() {
  const router = useRouter();
  const { data, isLoading } = useAlerts();
  const markRead = useMarkAlertsRead();
  const [pendingMarkAll, setPendingMarkAll] = useState<string[] | null>(null);

  const alerts = useMemo(() => data?.alerts ?? [], [data?.alerts]);
  const unreadCount = data?.unreadCount ?? 0;

  useEffect(() => {
    if (!pendingMarkAll) return;
    const timer = setTimeout(() => {
      markRead.mutate(pendingMarkAll);
      setPendingMarkAll(null);
    }, 5000);
    return () => clearTimeout(timer);
  }, [pendingMarkAll, markRead]);

  const handleAlertClick = useCallback(
    (alert: AlertResponse) => {
      if (!alert.is_read) {
        markRead.mutate([alert.id]);
      }
      if (alert.ticker) {
        router.push(`/stocks/${alert.ticker}`);
      }
    },
    [markRead, router],
  );

  const handleMarkAllRead = useCallback(() => {
    const unreadIds = alerts.filter((a) => !a.is_read).map((a) => a.id);
    if (unreadIds.length === 0) return;
    setPendingMarkAll(unreadIds);
  }, [alerts]);

  const handleUndo = useCallback(() => {
    setPendingMarkAll(null);
  }, []);

  return (
    <Popover>
      <PopoverTrigger
        render={
          <button className="relative p-2 rounded-md hover:bg-muted/50 transition-colors">
            <Bell className="h-5 w-5 text-muted-foreground" />
            {unreadCount > 0 && (
              <span className="absolute -top-0.5 -right-0.5 bg-loss text-white text-[10px] font-bold rounded-full min-w-[18px] h-[18px] flex items-center justify-center px-1">
                {unreadCount > 99 ? "99+" : unreadCount}
              </span>
            )}
          </button>
        }
      />
      <PopoverContent
        align="end"
        className="w-[380px] p-0 max-h-[400px] flex flex-col"
      >
        <div className="flex justify-between items-center px-4 py-3 border-b border-border">
          <span className="font-semibold text-sm">Notifications</span>
          {unreadCount > 0 && !pendingMarkAll && (
            <button
              onClick={handleMarkAllRead}
              className="text-cyan text-xs hover:underline"
            >
              Mark all read
            </button>
          )}
        </div>

        {pendingMarkAll && (
          <div className="flex justify-between items-center px-4 py-2 bg-muted/50 border-b border-border text-xs">
            <span className="text-muted-foreground">Marked all read.</span>
            <button onClick={handleUndo} className="text-cyan hover:underline">
              Undo
            </button>
          </div>
        )}

        <div className="overflow-y-auto flex-1">
          {isLoading ? (
            <AlertSkeleton />
          ) : alerts.length === 0 ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground text-sm">
              No notifications
            </div>
          ) : (
            alerts.map((alert) => (
              <AlertItem
                key={alert.id}
                alert={alert}
                onClick={handleAlertClick}
              />
            ))
          )}
        </div>

        {alerts.length > 0 && (
          <div className="px-4 py-2.5 border-t border-border text-center">
            <span className="text-cyan text-xs cursor-pointer hover:underline">
              View all notifications →
            </span>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
