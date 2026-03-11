// ErrorState — companion to EmptyState, shown when a query fails.

import { AlertCircleIcon } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ErrorStateProps {
  error?: string;
  onRetry?: () => void;
}

export function ErrorState({
  error = "Something went wrong",
  onRetry,
}: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
      <AlertCircleIcon className="size-8 text-destructive" aria-hidden="true" />
      <p className="text-sm text-muted-foreground">{error}</p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
