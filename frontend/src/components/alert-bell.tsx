"use client";

import { useState } from "react";
import { Bell, CheckCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAlerts, useUnreadAlertCount, useMarkAlertsRead } from "@/hooks/use-alerts";
import {
  Popover,
  PopoverTrigger,
  PopoverContent,
} from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import type { AlertResponse } from "@/types/api";

const SEVERITY_COLORS = {
  critical: "text-loss",
  warning: "text-warning",
  info: "text-cyan",
} as const;

function AlertItem({ alert }: { alert: AlertResponse }) {
  const severity = alert.severity as keyof typeof SEVERITY_COLORS;
  const color = SEVERITY_COLORS[severity] ?? "text-subtle";
  const timeAgo = getTimeAgo(alert.created_at);

  return (
    <div
      className={cn(
        "flex gap-2 px-3 py-2.5 border-b border-border last:border-0",
        !alert.is_read && "bg-card2"
      )}
    >
      <div className={cn("mt-0.5 shrink-0", color)}>
        {!alert.is_read && (
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-cyan" />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-xs font-medium text-foreground truncate">
          {alert.title}
        </div>
        <div className="text-[10px] text-subtle mt-0.5 line-clamp-2">
          {alert.message}
        </div>
        <div className="flex items-center gap-2 mt-1">
          {alert.ticker && (
            <span className="font-mono text-[9px] text-cyan">{alert.ticker}</span>
          )}
          <span className="text-[9px] text-subtle">{timeAgo}</span>
        </div>
      </div>
    </div>
  );
}

function getTimeAgo(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;
  const mins = Math.floor(diffMs / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function AlertBell() {
  const [open, setOpen] = useState(false);
  const { data: alerts } = useAlerts();
  const { data: unreadData } = useUnreadAlertCount();
  const markRead = useMarkAlertsRead();

  const unreadCount = unreadData?.unread_count ?? 0;

  function handleMarkAllRead() {
    if (!alerts) return;
    const unreadIds = alerts.filter((a) => !a.is_read).map((a) => a.id);
    if (unreadIds.length > 0) {
      markRead.mutate(unreadIds);
    }
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <button className="relative flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-hov hover:text-foreground transition-colors">
            <Bell size={16} />
            {unreadCount > 0 && (
              <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-loss px-1 text-[9px] font-bold text-white">
                {unreadCount > 99 ? "99+" : unreadCount}
              </span>
            )}
          </button>
        }
      />
      <PopoverContent
        align="end"
        className="w-80 p-0 border border-border bg-card shadow-xl"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-3 py-2 border-b border-border">
          <span className="text-xs font-semibold text-foreground">
            Notifications
          </span>
          {unreadCount > 0 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleMarkAllRead}
              className="h-6 px-2 text-[10px] text-subtle hover:text-foreground"
            >
              <CheckCheck size={12} className="mr-1" />
              Mark all read
            </Button>
          )}
        </div>

        {/* Alert list */}
        <div className="max-h-80 overflow-y-auto">
          {alerts && alerts.length > 0 ? (
            alerts.slice(0, 20).map((alert) => (
              <AlertItem key={alert.id} alert={alert} />
            ))
          ) : (
            <div className="py-8 text-center text-xs text-subtle">
              No notifications
            </div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
