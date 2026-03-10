// SectionHeading — standardized section label used throughout the app.
// Replaces the inline pattern: text-sm font-medium uppercase tracking-wider text-muted-foreground

import { TYPOGRAPHY } from "@/lib/typography";
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
      <h2 className={TYPOGRAPHY.SECTION_HEADING}>{children}</h2>
      {action && <div>{action}</div>}
    </div>
  );
}
