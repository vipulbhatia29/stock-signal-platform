"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { PageTransition } from "@/components/motion-primitives";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { useCurrentUser } from "@/hooks/use-current-user";
import { useAdminKpis } from "@/hooks/use-admin-observability";
import { HealthStrip } from "./_components/health-strip";
import { ErrorStream } from "./_components/error-stream";
import { AnomalyFindings } from "./_components/anomaly-findings";
import { ExternalApiDashboard } from "./_components/external-api-dashboard";
import { CostBreakdown } from "./_components/cost-breakdown";
import { PipelineHealth } from "./_components/pipeline-health";
import { DqScanner } from "./_components/dq-scanner";
import { TraceExplorer } from "./_components/trace-explorer";

type TabKey = "overview" | "apis-cost" | "infrastructure" | "trace-explorer";

export default function ObservabilityAdminClient() {
  const router = useRouter();
  const { isAdmin, isLoading: userLoading } = useCurrentUser();
  const { data: kpisEnvelope, isLoading: kpisLoading, error: kpisError } = useAdminKpis();

  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const [pendingTraceId, setPendingTraceId] = useState<string | null>(null);

  useEffect(() => {
    if (!userLoading && !isAdmin) {
      router.replace("/dashboard");
    }
  }, [userLoading, isAdmin, router]);

  useEffect(() => {
    if (pendingTraceId && activeTab === "trace-explorer") {
      const timer = setTimeout(() => setPendingTraceId(null), 100);
      return () => clearTimeout(timer);
    }
  }, [pendingTraceId, activeTab]);

  if (userLoading || (!isAdmin && !userLoading)) {
    return null;
  }

  const openTrace = (traceId: string) => {
    setPendingTraceId(traceId);
    setActiveTab("trace-explorer");
  };

  return (
    <PageTransition className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Observability
          </h1>
          <p className="text-sm text-subtle mt-1">
            Platform health and diagnostics
          </p>
        </div>
      </div>

      {/* Zone 1: Health Strip — always visible */}
      <HealthStrip
        data={kpisEnvelope?.result}
        isLoading={kpisLoading}
        error={kpisError}
      />

      {/* Tab navigation */}
      <Tabs
        value={activeTab}
        onValueChange={(v) => setActiveTab(v as TabKey)}
      >
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="apis-cost">APIs & Cost</TabsTrigger>
          <TabsTrigger value="infrastructure">Infrastructure</TabsTrigger>
          <TabsTrigger value="trace-explorer">Trace Explorer</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4 space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <ErrorStream onOpenTrace={openTrace} />
            <AnomalyFindings onOpenTrace={openTrace} />
          </div>
        </TabsContent>

        <TabsContent value="apis-cost" className="mt-4 space-y-4">
          <ExternalApiDashboard />
          <CostBreakdown onOpenTrace={openTrace} />
        </TabsContent>

        <TabsContent value="infrastructure" className="mt-4 space-y-4">
          <PipelineHealth />
          <DqScanner />
        </TabsContent>

        <TabsContent value="trace-explorer" className="mt-4 space-y-4">
          <TraceExplorer initialTraceId={pendingTraceId} />
        </TabsContent>
      </Tabs>
    </PageTransition>
  );
}

export { type TabKey };
export type OpenTraceFn = (traceId: string) => void;
