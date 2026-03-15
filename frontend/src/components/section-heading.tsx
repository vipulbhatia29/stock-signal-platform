// SectionHeading — standardized section label used throughout the app.
// Replaces the inline pattern: text-sm font-medium uppercase tracking-wider text-muted-foreground

import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

interface SectionHeadingProps {
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function SectionHeading({ children, action, className }: SectionHeadingProps) {
  return (
    <div className={cn("mb-3 flex items-center justify-between", className)}>
      <h2 className="text-[9.5px] font-semibold uppercase tracking-[0.1em] text-subtle">{children}</h2>
      {action && <div>{action}</div>}
    </div>
  );
}
