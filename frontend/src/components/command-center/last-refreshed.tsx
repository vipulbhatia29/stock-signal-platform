"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

interface LastRefreshedProps {
  timestamp: string | undefined;
}

function secondsAgo(isoTimestamp: string): number {
  return Math.floor((Date.now() - new Date(isoTimestamp).getTime()) / 1000);
}

function LastRefreshedInner({ timestamp }: { timestamp: string }) {
  const [ago, setAgo] = useState<number>(() => secondsAgo(timestamp));

  useEffect(() => {
    const id = setInterval(() => setAgo(secondsAgo(timestamp)), 1000);
    return () => clearInterval(id);
  }, [timestamp]);

  let color: string;
  if (ago < 30) {
    color = "text-emerald-400";
  } else if (ago < 60) {
    color = "text-yellow-400";
  } else {
    color = "text-red-500";
  }

  return (
    <span data-testid="last-refreshed" className={cn("text-xs", color)}>
      Updated {ago}s ago
    </span>
  );
}

export function LastRefreshed({ timestamp }: LastRefreshedProps) {
  if (!timestamp) {
    return (
      <span data-testid="last-refreshed" className="text-xs text-subtle">
        Loading...
      </span>
    );
  }

  return <LastRefreshedInner key={timestamp} timestamp={timestamp} />;
}
