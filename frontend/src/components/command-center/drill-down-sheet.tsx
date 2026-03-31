"use client";

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { RefreshCw } from "lucide-react";

interface DrillDownSheetProps {
  open: boolean;
  onClose: () => void;
  title: string;
  onRefresh?: () => void;
  isRefreshing?: boolean;
  children: React.ReactNode;
}

export function DrillDownSheet({
  open,
  onClose,
  title,
  onRefresh,
  isRefreshing,
  children,
}: DrillDownSheetProps) {
  return (
    <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
      <SheetContent
        side="right"
        className="w-full sm:max-w-[640px] flex flex-col"
        showCloseButton
      >
        <SheetHeader className="flex flex-row items-center justify-between gap-2 border-b border-border pb-3">
          <SheetTitle className="text-lg font-semibold">{title}</SheetTitle>
          {onRefresh && (
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={onRefresh}
              disabled={isRefreshing}
              aria-label="Refresh"
            >
              <RefreshCw
                className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`}
              />
            </Button>
          )}
        </SheetHeader>
        <div className="flex-1 overflow-y-auto p-4">{children}</div>
      </SheetContent>
    </Sheet>
  );
}
