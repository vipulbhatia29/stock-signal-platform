"use client";

import { useState } from "react";
import type { ChatSession } from "@/types/api";

interface SessionListProps {
  sessions: ChatSession[];
  activeId: string | null;
  onSwitch: (sessionId: string) => void;
  onDelete: (sessionId: string) => void;
  onNew: () => void;
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function SessionList({ sessions, activeId, onSwitch, onDelete, onNew }: SessionListProps) {
  const [expiredPromptId, setExpiredPromptId] = useState<string | null>(null);

  const handleClick = (session: ChatSession) => {
    if (!session.is_active) {
      setExpiredPromptId(session.id);
      return;
    }
    onSwitch(session.id);
  };

  return (
    <div className="flex flex-col">
      <button
        onClick={onNew}
        className="mx-3 mb-2 rounded-md border border-dashed border-accent/50 px-3 py-2 text-xs text-accent hover:bg-accent/5 transition-colors"
      >
        + New Chat
      </button>
      <div className="max-h-48 overflow-y-auto">
        {sessions.map((session) => (
          <div key={session.id}>
            <div
              className={`group flex items-center justify-between gap-2 px-3 py-2 text-xs cursor-pointer transition-colors ${
                session.id === activeId
                  ? "bg-accent/10 text-foreground"
                  : "text-muted-foreground hover:bg-muted"
              }`}
              onClick={() => handleClick(session)}
            >
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium">
                  {session.title ?? "Untitled"}
                </div>
                <div className="flex items-center gap-1.5 text-[10px]">
                  <span className={`rounded px-1 py-0.5 ${
                    session.agent_type === "stock"
                      ? "bg-accent/10 text-accent"
                      : "bg-muted text-muted-foreground"
                  }`}>
                    {session.agent_type === "stock" ? "Stock" : "General"}
                  </span>
                  <span>{timeAgo(session.last_active_at)}</span>
                  {!session.is_active && (
                    <span className="text-destructive">Expired</span>
                  )}
                </div>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(session.id);
                }}
                className="shrink-0 rounded p-1 opacity-0 group-hover:opacity-100 hover:bg-destructive/10 hover:text-destructive transition-all"
                aria-label="Delete session"
              >
                <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            {/* Expired session warning prompt */}
            {expiredPromptId === session.id && (
              <div className="mx-3 mb-1 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs">
                <p className="text-destructive mb-1.5">This session has expired.</p>
                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      setExpiredPromptId(null);
                      onNew();
                    }}
                    className="rounded bg-accent px-2 py-1 text-[10px] font-medium text-background hover:bg-accent/80 transition-colors"
                  >
                    Start New Chat
                  </button>
                  <button
                    onClick={() => {
                      setExpiredPromptId(null);
                      onSwitch(session.id);
                    }}
                    className="rounded border border-border px-2 py-1 text-[10px] text-muted-foreground hover:text-foreground transition-colors"
                  >
                    View Anyway
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
