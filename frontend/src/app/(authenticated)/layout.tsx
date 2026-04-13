"use client";

import { useState, useCallback } from "react";
import { SidebarNav } from "@/components/sidebar-nav";
import { Topbar } from "@/components/topbar";
import { ChatPanel } from "@/components/chat-panel";
import { ArtifactBar } from "@/components/chat/artifact-bar";
import { ChatProvider, useChat } from "@/contexts/chat-context";
import { useAddToWatchlist, useWatchlist } from "@/hooks/use-stocks";
import { ApiRequestError } from "@/lib/api";
import { EmailVerificationBanner } from "@/components/email-verification-banner";
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

  const handleAddTicker = useCallback(
    async (ticker: string) => {
      const isInWatchlist = watchlist?.some((w) => w.ticker === ticker);
      if (isInWatchlist) {
        toast.info(`${ticker} is already in your watchlist`);
        return;
      }
      toast.loading(`Adding ${ticker} to watchlist…`, { id: `add-${ticker}` });
      try {
        await addToWatchlist.mutateAsync(ticker);
        toast.success(`${ticker} added to watchlist`, { id: `add-${ticker}` });
      } catch (err) {
        if (err instanceof ApiRequestError && err.status === 409) {
          toast.info(err.detail, { id: `add-${ticker}` });
        } else {
          toast.error(`Failed to add ${ticker} to watchlist`, { id: `add-${ticker}` });
        }
      }
    },
    [watchlist, addToWatchlist]
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
