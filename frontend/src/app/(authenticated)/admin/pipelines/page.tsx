"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { PageTransition } from "@/components/motion-primitives";
import { Skeleton } from "@/components/ui/skeleton";
import { useCurrentUser } from "@/hooks/use-current-user";
import {
  usePipelineGroups,
  useActiveRun,
  useTriggerGroup,
} from "@/hooks/use-admin-pipelines";
import type { PipelineGroup } from "@/hooks/use-admin-pipelines";
import { PipelineGroupCard } from "@/components/admin/pipeline-group-card";
import { PipelineRunHistory } from "@/components/admin/pipeline-run-history";
import { CacheControls } from "@/components/admin/cache-controls";

function LoadingSkeleton() {
  return (
    <div className="space-y-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <Skeleton key={i} className="h-[80px] w-full rounded-xl bg-card2" />
      ))}
    </div>
  );
}

// Wrapper that adds active run polling per group
function PipelineGroupCardWithActiveRun({
  group,
  onTrigger,
  isTriggering,
  onSelect,
}: {
  group: PipelineGroup;
  onTrigger: (group: string) => void;
  isTriggering: boolean;
  onSelect: () => void;
}) {
  const { data: activeRun } = useActiveRun(group.name);
  return (
    <div onClick={onSelect}>
      <PipelineGroupCard
        group={group}
        activeRun={activeRun ?? null}
        onTrigger={onTrigger}
        isTriggering={isTriggering}
      />
    </div>
  );
}

export default function PipelinesPage() {
  const router = useRouter();
  const { isAdmin, isLoading: userLoading } = useCurrentUser();
  const { data, isLoading, error } = usePipelineGroups();
  const triggerGroup = useTriggerGroup();
  const [selectedGroup, setSelectedGroup] = useState<string>("");

  useEffect(() => {
    if (!userLoading && !isAdmin) {
      router.replace("/dashboard");
    }
  }, [userLoading, isAdmin, router]);

  if (userLoading || (!isAdmin && !userLoading)) return null;

  const handleTrigger = (group: string) => {
    triggerGroup.mutate({ group, failureMode: "continue" });
    setSelectedGroup(group);
  };

  return (
    <PageTransition className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Pipeline Control</h1>
          <p className="text-sm text-subtle mt-1">
            Manage background task groups, trigger runs, and clear caches
          </p>
        </div>
      </div>

      {isLoading ? (
        <LoadingSkeleton />
      ) : error ? (
        <div className="text-sm text-loss">Failed to load pipeline groups</div>
      ) : (
        <div className="space-y-6">
          {/* Task Groups */}
          <div className="space-y-3">
            <h2 className="text-[9px] uppercase tracking-wider text-subtle">
              Task Groups
            </h2>
            {data?.groups.map((group) => (
              <PipelineGroupCardWithActiveRun
                key={group.name}
                group={group}
                onTrigger={handleTrigger}
                isTriggering={triggerGroup.isPending}
                onSelect={() => setSelectedGroup(group.name)}
              />
            ))}
          </div>

          {/* Bottom section: History + Cache Controls side by side */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div>
              {selectedGroup ? (
                <PipelineRunHistory group={selectedGroup} />
              ) : (
                <div className="rounded-lg border border-border bg-card2 px-4 py-8 text-center text-sm text-subtle">
                  Select a group to view run history
                </div>
              )}
            </div>
            <CacheControls />
          </div>
        </div>
      )}
    </PageTransition>
  );
}
