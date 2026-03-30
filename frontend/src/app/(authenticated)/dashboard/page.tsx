"use client";

import { PageTransition } from "@/components/motion-primitives";
import { MigrationToast } from "@/components/migration-toast";
import { MarketPulseZone } from "./_components/market-pulse-zone";
import { SignalsZone } from "./_components/signals-zone";
import { PortfolioZone } from "./_components/portfolio-zone";
import { AlertsZone } from "./_components/alerts-zone";
import { NewsZone } from "./_components/news-zone";

/**
 * Daily Intelligence Briefing — 5-zone dashboard.
 *
 * Zone 1: Market Pulse — market status + index performance + movers
 * Zone 2: Your Signals — recommendations + top movers
 * Zone 3: Portfolio Overview — KPIs + health grade + sector bars
 * Zone 4: Alerts — recent alerts grid
 * Zone 5: News & Intelligence — personalized news links
 */
export default function DashboardPage() {
  return (
    <PageTransition className="space-y-6">
      <MigrationToast />

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
