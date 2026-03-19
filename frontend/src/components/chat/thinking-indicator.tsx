"use client";

interface ThinkingIndicatorProps {
  text?: string;
}

export function ThinkingIndicator({ text = "Analyzing..." }: ThinkingIndicatorProps) {
  return (
    <div className="flex items-center gap-2 px-4 py-2 text-sm text-muted-foreground">
      <div className="flex gap-1">
        <span className="h-1.5 w-1.5 rounded-full bg-accent animate-[pulse_1.4s_ease-in-out_infinite]" />
        <span className="h-1.5 w-1.5 rounded-full bg-accent animate-[pulse_1.4s_ease-in-out_0.2s_infinite]" />
        <span className="h-1.5 w-1.5 rounded-full bg-accent animate-[pulse_1.4s_ease-in-out_0.4s_infinite]" />
      </div>
      <span>{text}</span>
    </div>
  );
}
