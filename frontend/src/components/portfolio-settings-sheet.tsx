"use client";

import { useState } from "react";
import { Settings } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { usePreferences, useUpdatePreferences } from "@/hooks/use-stocks";
import type { UserPreferences } from "@/types/api";

const DEFAULTS: UserPreferences = {
  default_stop_loss_pct: 20,
  max_position_pct: 5,
  max_sector_pct: 30,
  min_cash_reserve_pct: 10,
};

/**
 * Inner form component — receives initial values as props to avoid
 * the setState-in-useEffect anti-pattern. Remounts when prefs change
 * via the parent's `key` prop.
 */
function SettingsForm({
  initial,
  onClose,
}: {
  initial: UserPreferences;
  onClose: () => void;
}) {
  const updateMutation = useUpdatePreferences();

  const [stopLoss, setStopLoss] = useState(initial.default_stop_loss_pct);
  const [maxPosition, setMaxPosition] = useState(initial.max_position_pct);
  const [maxSector, setMaxSector] = useState(initial.max_sector_pct);
  const [minCash, setMinCash] = useState(initial.min_cash_reserve_pct);

  function handleSave() {
    updateMutation.mutate(
      {
        default_stop_loss_pct: stopLoss,
        max_position_pct: maxPosition,
        max_sector_pct: maxSector,
      },
      { onSuccess: () => onClose() }
    );
  }

  function handleReset() {
    setStopLoss(DEFAULTS.default_stop_loss_pct);
    setMaxPosition(DEFAULTS.max_position_pct);
    setMaxSector(DEFAULTS.max_sector_pct);
    setMinCash(DEFAULTS.min_cash_reserve_pct);
  }

  return (
    <>
      <div className="grid gap-6 py-6">
        <div className="grid gap-2">
          <Label htmlFor="stop-loss">Stop-Loss Threshold (%)</Label>
          <Input
            id="stop-loss"
            type="number"
            min={1}
            max={100}
            step={1}
            value={stopLoss}
            onChange={(e) => setStopLoss(Number(e.target.value))}
          />
          <p className="text-xs text-muted-foreground">
            Alert when a position drops below this percentage loss.
          </p>
        </div>

        <div className="grid gap-2">
          <Label htmlFor="max-position">Max Position Size (%)</Label>
          <Input
            id="max-position"
            type="number"
            min={1}
            max={100}
            step={1}
            value={maxPosition}
            onChange={(e) => setMaxPosition(Number(e.target.value))}
          />
          <p className="text-xs text-muted-foreground">
            Alert when a single position exceeds this portfolio percentage.
          </p>
        </div>

        <div className="grid gap-2">
          <Label htmlFor="max-sector">Max Sector Concentration (%)</Label>
          <Input
            id="max-sector"
            type="number"
            min={1}
            max={100}
            step={1}
            value={maxSector}
            onChange={(e) => setMaxSector(Number(e.target.value))}
          />
          <p className="text-xs text-muted-foreground">
            Alert when any sector exceeds this portfolio percentage.
          </p>
        </div>

        <div className="grid gap-2">
          <Label htmlFor="min-cash" className="text-muted-foreground">
            Min Cash Reserve (%)
          </Label>
          <Input
            id="min-cash"
            type="number"
            value={minCash}
            disabled
            className="opacity-50"
          />
          <p className="text-xs text-muted-foreground">
            Coming soon — requires cash tracking.
          </p>
        </div>
      </div>

      <SheetFooter className="flex gap-2 sm:justify-between">
        <Button variant="ghost" onClick={handleReset}>
          Reset Defaults
        </Button>
        <Button onClick={handleSave} disabled={updateMutation.isPending}>
          {updateMutation.isPending ? "Saving..." : "Save"}
        </Button>
      </SheetFooter>
    </>
  );
}

export function PortfolioSettingsSheet() {
  const { data: prefs } = usePreferences();
  const [open, setOpen] = useState(false);

  const initial = prefs ?? DEFAULTS;

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger
        render={
          <Button variant="outline" size="icon" aria-label="Portfolio settings" />
        }
      >
        <Settings className="h-4 w-4" />
      </SheetTrigger>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>Portfolio Settings</SheetTitle>
          <SheetDescription>
            Configure divestment alert thresholds. Changes apply immediately to
            your portfolio alerts.
          </SheetDescription>
        </SheetHeader>
        <SettingsForm
          key={JSON.stringify(initial)}
          initial={initial}
          onClose={() => setOpen(false)}
        />
      </SheetContent>
    </Sheet>
  );
}
