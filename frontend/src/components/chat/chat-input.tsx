"use client";

import { useRef, useCallback, useImperativeHandle, forwardRef, type KeyboardEvent } from "react";

export interface ChatInputHandle {
  fillText: (text: string) => void;
}

interface ChatInputProps {
  onSend: (content: string) => void;
  onStop: () => void;
  isStreaming: boolean;
  disabled?: boolean;
}

export const ChatInput = forwardRef<ChatInputHandle, ChatInputProps>(
  function ChatInput({ onSend, onStop, isStreaming, disabled }, ref) {
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    useImperativeHandle(ref, () => ({
      fillText(text: string) {
        if (textareaRef.current) {
          textareaRef.current.value = text;
          textareaRef.current.focus();
          // Trigger auto-resize
          textareaRef.current.style.height = "auto";
          textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
        }
      },
    }));

    const handleSend = useCallback(() => {
      const value = textareaRef.current?.value.trim();
      if (!value) return;
      onSend(value);
      if (textareaRef.current) {
        textareaRef.current.value = "";
        textareaRef.current.style.height = "auto";
      }
    }, [onSend]);

    const handleKeyDown = useCallback(
      (e: KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          if (!isStreaming && !disabled) handleSend();
        }
      },
      [handleSend, isStreaming, disabled]
    );

    const handleInput = useCallback(() => {
      const el = textareaRef.current;
      if (!el) return;
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
    }, []);

    return (
      <div className="flex items-end gap-2 border-t border-border bg-card px-3 py-2">
        <textarea
          ref={textareaRef}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          placeholder="Ask about stocks, portfolio, signals..."
          disabled={disabled}
          rows={1}
          className="flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none disabled:opacity-50"
        />
        {isStreaming ? (
          <button
            onClick={onStop}
            aria-label="Stop generation"
            className="shrink-0 rounded-md bg-destructive/10 p-2 text-destructive hover:bg-destructive/20 transition-colors"
          >
            <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
              <rect x="6" y="6" width="12" height="12" rx="1" />
            </svg>
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={disabled}
            aria-label="Send message"
            className="shrink-0 rounded-md bg-accent p-2 text-white hover:bg-accent/90 transition-colors disabled:opacity-50"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 12 3.269 3.125A59.769 59.769 0 0 1 21.485 12 59.768 59.768 0 0 1 3.27 20.875L5.999 12Zm0 0h7.5" />
            </svg>
          </button>
        )}
      </div>
    );
  }
);
