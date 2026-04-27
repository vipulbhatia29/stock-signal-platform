"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { SidebarNav } from "@/components/sidebar-nav";
import { Topbar } from "@/components/topbar";
import { ChatPanel } from "@/components/chat-panel";
import { ArtifactBar } from "@/components/chat/artifact-bar";
import { ChatProvider, useChat } from "@/contexts/chat-context";
import { useAddToWatchlist, useWatchlist, useIngestTicker } from "@/hooks/use-stocks";
import { ApiRequestError } from "@/lib/api";
import { EmailVerificationBanner } from "@/components/email-verification-banner";
import { IngestProgressToast } from "@/components/ingest-progress-toast";
import { toast } from "sonner";

function AuthenticatedShell({ children }: { children: React.ReactNode }) {
  const { chatOpen, setChatOpen } = useChat();
  const [artifact, setArtifact] = useState<{
    tool: string;
    params: Record<string, unknown>;
    data: unknown;
  } | null>(null);
  const { data: watchlist } = useWatchlist();
  const addToWatchlist = useAddToWatchlist();
  const ingestTicker = useIngestTicker();
  const router = useRouter();

  const handleAddTicker = useCallback(
    async (ticker: string) => {
      const upperTicker = ticker.toUpperCase();
      const existing = watchlist?.find((w) => w.ticker === upperTicker);
      if (existing) {
        // Already in watchlist — navigate to stock detail
        router.push(`/stocks/${upperTicker}`);
        return;
      }
      toast.loading(`Adding ${upperTicker} to watchlist…`, { id: `add-${ticker}` });
      try {
        await addToWatchlist.mutateAsync(ticker);
        toast.dismiss(`add-${ticker}`);
        // Start ingest pipeline for new tickers
        toast.custom(
          (t) => (
            <IngestProgressToast
              ticker={upperTicker}
              onComplete={() => {
                toast.dismiss(t);
                router.push(`/stocks/${upperTicker}`);
              }}
            />
          ),
          { duration: Infinity, id: `ingest-${ticker}` },
        );
        // Fire ingest in background (toast tracks progress)
        ingestTicker.mutate(upperTicker);
      } catch (err) {
        if (err instanceof ApiRequestError && err.status === 409) {
          // Already exists (race condition) — navigate anyway
          toast.dismiss(`add-${ticker}`);
          toast.info(`${upperTicker} already in watchlist`);
          router.push(`/stocks/${upperTicker}`);
        } else {
          toast.error(`Failed to add ${upperTicker}`, { id: `add-${ticker}` });
        }
      }
    },
    [watchlist, addToWatchlist, ingestTicker, router]
  );

  return (
    <div className="flex overflow-hidden" style={{ height: "100vh" }}>
      <SidebarNav />

      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Topbar onAddTicker={handleAddTicker} />
        <EmailVerificationBanner />
        {artifact && (
          <ArtifactBar artifact={artifact} onDismiss={() => setArtifact(null)} />
        )}
        <main className="flex-1 overflow-y-auto scrollbar-thin">
          <div className="px-4 py-6 animate-fade-in">{children}</div>
        </main>
      </div>

      <ChatPanel
        isOpen={chatOpen}
        onClose={() => setChatOpen(false)}
        onArtifact={setArtifact}
      />
    </div>
  );
}

export default function AuthenticatedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ChatProvider>
      <AuthenticatedShell>{children}</AuthenticatedShell>
    </ChatProvider>
  );
}
