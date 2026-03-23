"use client";

interface DeclineMessageProps {
  content: string;
}

export function DeclineMessage({ content }: DeclineMessageProps) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-3">
      <div className="flex items-start gap-2">
        <span className="mt-0.5 text-[var(--color-muted-foreground)]">🔒</span>
        <p className="text-sm text-[var(--color-muted-foreground)]">{content}</p>
      </div>
    </div>
  );
}
