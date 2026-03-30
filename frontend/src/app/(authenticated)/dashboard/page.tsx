"use client";

import { useState } from "react";
import { toast } from "sonner";
import { PageTransition } from "@/components/motion-primitives";
import { WelcomeBanner } from "@/components/welcome-banner";
import { TrendingStocks } from "@/components/trending-stocks";
import { useAddToWatchlist } from "@/hooks/use-stocks";
import * as api from "@/lib/api";
import { MarketPulseZone } from "./_components/market-pulse-zone";
import { SignalsZone } from "./_components/signals-zone";
import { PortfolioZone } from "./_components/portfolio-zone";
import { AlertsZone } from "./_components/alerts-zone";
import { NewsZone } from "./_components/news-zone";

/**
 * Daily Intelligence Briefing — 5-zone dashboard.
 *
 * Zone 1: Market Pulse — market status + index performance
 * Zone 2: Your Signals — recommendations + top movers
 * Zone 3: Portfolio Overview — KPIs + allocation + sector bars
 * Zone 4: Alerts — recent alerts grid
 * Zone 5: News & Intelligence — personalized news links
 */
export default function DashboardPage() {
  const [addingTickers, setAddingTickers] = useState<Set<string>>(new Set());
  const addToWatchlist = useAddToWatchlist();

  const handleQuickAdd = async (ticker: string) => {
    setAddingTickers((prev) => new Set(prev).add(ticker));
    try {
      await api.post(`/stocks/${ticker}/ingest`);
      addToWatchlist.mutate(ticker);
    } catch {
      toast.error(`Failed to add ${ticker}`);
    } finally {
      setAddingTickers((prev) => {
        const next = new Set(prev);
        next.delete(ticker);
        return next;
      });
    }
  };

  return (
    <PageTransition className="space-y-6">
      {/* Welcome Banner (new users) */}
      <WelcomeBanner onAddTicker={handleQuickAdd} addingTickers={addingTickers} />

      {/* Trending Stocks (visible even with empty watchlist) */}
      <TrendingStocks />

      {/* Zone 1: Market Pulse */}
      <MarketPulseZone />

      {/* Zone 2: Your Signals + Top Movers */}
      <SignalsZone />

      {/* Zone 3: Portfolio Overview */}
      <PortfolioZone />

      {/* Zone 4 + 5: Alerts and News side by side on desktop */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Zone 4: Alerts */}
        <AlertsZone />

        {/* Zone 5: News & Intelligence */}
        <NewsZone />
      </div>
    </PageTransition>
  );
}
