"use client";

import { useEffect } from "react";
import { toast } from "sonner";

/**
 * One-time toast notifying users that the watchlist has moved
 * from the dashboard to the Screener page's Watchlist tab.
 * Renders nothing — side-effect only.
 */
export function MigrationToast() {
  useEffect(() => {
    const key = "dashboard-watchlist-migration-v1";
    if (typeof window !== "undefined" && !localStorage.getItem(key)) {
      localStorage.setItem(key, "true");
      toast.info("Your watchlist has moved to the Screener page.", {
        description: "Use the Watchlist tab to see your tracked stocks.",
        duration: 8000,
      });
    }
  }, []);

  return null;
}
