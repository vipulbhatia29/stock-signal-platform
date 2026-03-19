"use client";

interface ErrorBubbleProps {
  error: string;
  onRetry: () => void;
}

export function ErrorBubble({ error, onRetry }: ErrorBubbleProps) {
  return (
    <div className="mx-4 my-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-2 text-sm">
          <svg
            className="mt-0.5 h-4 w-4 shrink-0 text-destructive"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z"
            />
          </svg>
          <span className="text-destructive">{error}</span>
        </div>
        <button
          onClick={onRetry}
          className="shrink-0 rounded px-2 py-1 text-xs font-medium text-accent hover:bg-accent/10 transition-colors"
        >
          Try Again
        </button>
      </div>
    </div>
  );
}
