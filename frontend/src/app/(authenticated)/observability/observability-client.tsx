"use client";

import { Suspense } from "react";
import { PageTransition } from "@/components/motion-primitives";
import { Skeleton } from "@/components/ui/skeleton";
import { useCurrentUser } from "@/hooks/use-current-user";
import { KPIStrip } from "./_components/kpi-strip";
import { AnalyticsCharts } from "./_components/analytics-charts";
import { QueryTable } from "./_components/query-table";
import { AssessmentSection } from "./_components/assessment-section";

export function ObservabilityClient() {
  const { isAdmin } = useCurrentUser();

  return (
    <PageTransition className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Observability</h1>

      <KPIStrip />
      <Suspense fallback={<Skeleton className="h-[320px] w-full rounded-lg bg-card2" />}>
        <AnalyticsCharts isAdmin={isAdmin} />
      </Suspense>
      <Suspense fallback={<Skeleton className="h-[400px] w-full rounded-lg bg-card2" />}>
        <QueryTable isAdmin={isAdmin} />
      </Suspense>
      <AssessmentSection isAdmin={isAdmin} />
    </PageTransition>
  );
}
