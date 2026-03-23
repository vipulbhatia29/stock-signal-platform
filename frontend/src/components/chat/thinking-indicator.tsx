"use client";

interface ThinkingIndicatorProps {
  text?: string;
}

export function ThinkingIndicator({ text = "Analyzing your question..." }: ThinkingIndicatorProps) {
  return (
    <div className="flex items-center gap-2.5 px-4 py-2.5 text-sm text-muted-foreground">
      <div className="flex gap-1">
        <span className="h-2 w-2 rounded-full bg-cyan animate-pulse-subtle" />
        <span className="h-2 w-2 rounded-full bg-cyan animate-pulse-subtle" style={{ animationDelay: "0.3s" }} />
        <span className="h-2 w-2 rounded-full bg-cyan animate-pulse-subtle" style={{ animationDelay: "0.6s" }} />
      </div>
      <span className="text-xs">{text}</span>
    </div>
  );
}
