"use client";

import { useEffect, useRef } from "react";
import { SendIcon, XIcon } from "lucide-react";
import { STORAGE_KEYS } from "@/lib/storage-keys";

interface ChatPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

const SUGGESTIONS = [
  "Analyze my portfolio",
  "Best signals today",
  "What's happening with NVDA?",
  "Top sector momentum",
];

const STUB_MESSAGE =
  "Hi! I'm your AI analyst. Ask me anything about your portfolio or watchlist. (Full AI integration coming soon)";

export function ChatPanel({ isOpen, onClose }: ChatPanelProps) {
  const asideRef = useRef<HTMLElement>(null);
  const handleRef = useRef<HTMLDivElement>(null);

  // Restore saved width and set up drag-resize
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
        const delta = startX - e.clientX; // left drag = wider
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

  return (
    <aside
      ref={asideRef}
      className="flex flex-col border-l border-border bg-card flex-shrink-0 relative overflow-hidden"
      style={{
        width: "var(--cp)",
        minWidth: "var(--cp)",
        transform: isOpen ? "translateX(0)" : "translateX(100%)",
        transition: "transform 0.25s cubic-bezier(.22,.68,0,1.1)",
      }}
    >
      {/* Drag resize handle */}
      <div
        ref={handleRef}
        className="absolute left-0 top-0 bottom-0 w-[5px] cursor-col-resize z-10 hover:bg-[var(--bhi)] transition-colors"
      />

      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3.5 border-b border-border flex-shrink-0">
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
        <button
          onClick={onClose}
          className="w-6 h-6 rounded-[5px] bg-hov border border-border text-muted-foreground hover:text-foreground flex items-center justify-center text-xs"
          aria-label="Close AI panel"
        >
          <XIcon size={12} />
        </button>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3.5 py-3.5 flex flex-col gap-2.5">
        {/* Bot greeting */}
        <div className="flex flex-col gap-0.5">
          <div className="max-w-[85%] px-[11px] py-2 rounded-[10px] rounded-bl-[3px] bg-card2 border border-border text-foreground text-[12px] leading-relaxed">
            {STUB_MESSAGE}
          </div>
          <span className="text-[9.5px] text-subtle px-1">AI Analyst</span>
        </div>
      </div>

      {/* Suggested prompts */}
      <div className="flex flex-wrap gap-1.5 px-3.5 py-2 border-t border-border flex-shrink-0">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            className="bg-card2 border border-border text-muted-foreground hover:border-[var(--bhi)] hover:text-cyan px-2.5 py-1 rounded-full text-[10.5px] transition-colors whitespace-nowrap"
            disabled
            title="Coming soon — Phase 4"
          >
            {s}
          </button>
        ))}
      </div>

      {/* Input */}
      <div className="flex items-center gap-2 px-3.5 py-2.5 border-t border-border flex-shrink-0">
        <textarea
          className="flex-1 bg-card2 border border-border rounded-lg px-3 py-1.5 text-foreground text-[12px] resize-none outline-none focus:border-[var(--bhi)] placeholder:text-subtle"
          placeholder="Ask about your portfolio... (coming soon)"
          rows={1}
          disabled
        />
        <button
          className="w-8 h-8 rounded-lg bg-cyan flex items-center justify-center flex-shrink-0 opacity-40 cursor-not-allowed"
          disabled
          aria-label="Send message"
        >
          <SendIcon size={14} className="text-[var(--background)]" />
        </button>
      </div>
    </aside>
  );
}
