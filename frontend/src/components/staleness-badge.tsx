"use client";

import { Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";

interface StalenessBadgeProps {
  lastUpdated: string | null;
  slaHours: number;
  refreshing?: boolean;
}

function getAgeHours(isoTimestamp: string): number {
  return (Date.now() - new Date(isoTimestamp).getTime()) / 3_600_000;
}

/**
 * Render a stale/refreshing badge. Returns null when within SLA.
 */
export function StalenessBadge({ lastUpdated, slaHours, refreshing }: StalenessBadgeProps) {
  if (refreshing) {
    return (
      <Badge variant="default" data-testid="staleness-badge-refreshing">
        <Loader2 className="mr-1 h-3 w-3 animate-spin" />
        Refreshing
      </Badge>
    );
  }
  if (!lastUpdated) {
    return (
      <Badge variant="outline" data-testid="staleness-badge-none">
        No data
      </Badge>
    );
  }
  const ageHours = getAgeHours(lastUpdated);
  if (ageHours > slaHours * 2) {
    return (
      <Badge variant="destructive" data-testid="staleness-badge-very-stale">
        Very stale ({Math.round(ageHours)}h old)
      </Badge>
    );
  }
  if (ageHours > slaHours) {
    return (
      <Badge variant="secondary" data-testid="staleness-badge-stale">
        Stale ({Math.round(ageHours)}h old)
      </Badge>
    );
  }
  return null;
}
