"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import { XIcon, Sparkles } from "lucide-react";
import { STORAGE_KEYS } from "@/lib/storage-keys";
import { useStreamChat } from "@/hooks/use-stream-chat";
import { useChatSessions, useDeleteSession } from "@/hooks/use-chat";
import { shouldPin } from "@/components/chat/artifact-bar";
import { MessageBubble } from "@/components/chat/message-bubble";
import { ThinkingIndicator } from "@/components/chat/thinking-indicator";
import { ErrorBubble } from "@/components/chat/error-bubble";
import { AgentSelector } from "@/components/chat/agent-selector";
import { SessionList } from "@/components/chat/session-list";
import { ChatInput, type ChatInputHandle } from "@/components/chat/chat-input";

interface ChatPanelProps {
  isOpen: boolean;
  onClose: () => void;
  onArtifact: (artifact: { tool: string; params: Record<string, unknown>; data: unknown } | null) => void;
}

const SUGGESTIONS = [
  "Analyze my portfolio",
  "Best signals today",
  "What's happening with NVDA?",
  "Top sector momentum",
];

export function ChatPanel({ isOpen, onClose, onArtifact }: ChatPanelProps) {
  const asideRef = useRef<HTMLElement>(null);
  const chatInputRef = useRef<ChatInputHandle>(null);
  const handleRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const isUserScrolledUp = useRef(false);
  const [showSessions, setShowSessions] = useState(false);

  const {
    messages,
    isStreaming,
    error,
    activeSessionId,
    agentType,
    sendMessage,
    stopGeneration,
    retry,
    switchSession,
    startNewSession,
    setAgentType,
  } = useStreamChat();

  const { data: sessions } = useChatSessions();
  const deleteSession = useDeleteSession();

  // Track manual scroll
  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    isUserScrolledUp.current = !atBottom;
  }, []);

  // Auto-scroll on new content
  useEffect(() => {
    if (!isUserScrolledUp.current) {
      messagesEndRef.current?.scrollIntoView?.({ behavior: "smooth" });
    }
  }, [messages]);

  // Artifact dispatch: only after streaming completes (not on every token flush)
  useEffect(() => {
    if (isStreaming) return;
    if (messages.length === 0) return;
    const lastMsg = messages[messages.length - 1];
    if (lastMsg.role !== "assistant") return;
    const completedPinnable = lastMsg.toolCalls.find(
      (tc) => tc.status === "completed" && shouldPin(tc.tool) && tc.result
    );
    if (completedPinnable) {
      onArtifact({
        tool: completedPinnable.tool,
        params: completedPinnable.params,
        data: completedPinnable.result,
      });
    }
  }, [isStreaming, messages, onArtifact]);

  // Drag-resize logic (preserved from stub)
  useEffect(() => {
    const savedWidth = localStorage.getItem(STORAGE_KEYS.CHAT_PANEL_WIDTH);
    if (savedWidth) {
      document.documentElement.style.setProperty("--cp", `${savedWidth}px`);
    }

    const handle = handleRef.current;
    const aside = asideRef.current;
    if (!handle || !aside) return;

    const onMouseDown = (e: MouseEvent) => {
      e.preventDefault();
      const startX = e.clientX;
      const startWidth = aside.offsetWidth;
      document.body.classList.add("resizing");

      const onMove = (e: MouseEvent) => {
        const delta = startX - e.clientX;
        const newWidth = Math.min(520, Math.max(240, startWidth + delta));
        document.documentElement.style.setProperty("--cp", `${newWidth}px`);
      };

      const onUp = () => {
        document.body.classList.remove("resizing");
        const currentWidth = document.documentElement.style
          .getPropertyValue("--cp")
          .replace("px", "");
        localStorage.setItem(STORAGE_KEYS.CHAT_PANEL_WIDTH, currentWidth);
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
      };

      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    };

    handle.addEventListener("mousedown", onMouseDown);
    return () => handle.removeEventListener("mousedown", onMouseDown);
  }, []);

  const handleSessionSwitch = useCallback(
    (sessionId: string) => {
      switchSession(sessionId);
      onArtifact(null);
    },
    [switchSession, onArtifact]
  );

  const handleNewSession = useCallback(() => {
    startNewSession(agentType);
    onArtifact(null);
  }, [startNewSession, agentType, onArtifact]);

  return (
    <aside
      ref={asideRef}
      className="flex flex-col border-l border-border bg-card flex-shrink-0 relative overflow-hidden"
      style={{
        width: isOpen ? "var(--cp)" : "0px",
        minWidth: isOpen ? "var(--cp)" : "0px",
        opacity: isOpen ? 1 : 0,
        transition: "width 0.25s cubic-bezier(.22,.68,0,1.1), min-width 0.25s cubic-bezier(.22,.68,0,1.1), opacity 0.2s ease",
      }}
    >
      {/* Drag resize handle */}
      <div
        ref={handleRef}
        className="absolute left-0 top-0 bottom-0 w-[5px] cursor-col-resize z-10 hover:bg-[var(--bhi)] transition-colors"
      />

      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3.5 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-2">
          <div>
            <div className="flex items-center gap-2 text-[13px] font-semibold text-foreground">
              <span
                className="w-[7px] h-[7px] rounded-full bg-gain"
                style={{ boxShadow: "0 0 5px var(--gain)" }}
              />
              AI Analyst
            </div>
            <p className="text-[10px] text-subtle mt-0.5">Powered by Claude</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setShowSessions(!showSessions)}
            className="w-6 h-6 rounded-[5px] bg-hov border border-border text-muted-foreground hover:text-foreground flex items-center justify-center text-xs"
            aria-label="Toggle sessions"
            title="Chat history"
          >
            <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H8.25m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H12m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 0 1-2.555-.337A5.972 5.972 0 0 1 5.41 20.97a5.969 5.969 0 0 1-.474-.065 4.48 4.48 0 0 0 .978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25Z" />
            </svg>
          </button>
          <button
            onClick={onClose}
            className="w-6 h-6 rounded-[5px] bg-hov border border-border text-muted-foreground hover:text-foreground flex items-center justify-center text-xs"
            aria-label="Close AI panel"
          >
            <XIcon size={12} />
          </button>
        </div>
      </header>

      {/* Session list (collapsible) */}
      {showSessions && sessions && (
        <div className="border-b border-border py-2">
          <SessionList
            sessions={sessions}
            activeId={activeSessionId}
            onSwitch={handleSessionSwitch}
            onDelete={(id) => deleteSession.mutate(id)}
            onNew={handleNewSession}
          />
        </div>
      )}

      {/* Agent selector (shown when no active session) */}
      {!activeSessionId && messages.length === 0 && (
        <AgentSelector
          value={agentType}
          onChange={(agent) => setAgentType(agent)}
          disabled={isStreaming}
        />
      )}

      {/* Messages */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto flex flex-col"
      >
        {messages.length === 0 && !isStreaming && (
          <div className="flex-1 flex flex-col items-center justify-center px-4 text-center">
            <div className="text-muted-foreground text-sm mb-4">
              Ask me anything about your portfolio or the markets.
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            role={msg.role}
            content={msg.content}
            toolCalls={msg.toolCalls}
            isStreaming={msg.isStreaming}
            plan={msg.plan}
            evidence={msg.evidence}
            isDecline={msg.isDecline}
          />
        ))}

        {isStreaming && messages.length > 0 && messages[messages.length - 1].content === "" && messages[messages.length - 1].toolCalls.length === 0 && (
          <ThinkingIndicator />
        )}

        {error && <ErrorBubble error={error} onRetry={retry} />}

        <div ref={messagesEndRef} />
      </div>

      {/* Suggestion chips (shown when no messages) — fill input, don't auto-send */}
      {messages.length === 0 && !isStreaming && (
        <div className="px-3.5 py-2 border-t border-border flex-shrink-0 space-y-2">
          <div className="flex items-center gap-1.5 text-muted-foreground">
            <Sparkles size={12} className="text-cyan" />
            <span className="text-[10px]">Suggestions</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => chatInputRef.current?.fillText(s)}
                className="bg-card2 border border-border text-muted-foreground hover:border-[var(--bhi)] hover:text-cyan px-2.5 py-1 rounded-full text-[10.5px] transition-colors whitespace-nowrap"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <ChatInput
        ref={chatInputRef}
        onSend={sendMessage}
        onStop={stopGeneration}
        isStreaming={isStreaming}
      />
    </aside>
  );
}
