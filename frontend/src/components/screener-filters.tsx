"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Button } from "@/components/ui/button";
import type { IndexResponse } from "@/types/api";

const RSI_OPTIONS = [
  { value: "__all__", label: "RSI: All" },
  { value: "OVERSOLD", label: "Oversold" },
  { value: "NEUTRAL", label: "Neutral" },
  { value: "OVERBOUGHT", label: "Overbought" },
];

const MACD_OPTIONS = [
  { value: "__all__", label: "MACD: All" },
  { value: "BULLISH", label: "Bullish" },
  { value: "BEARISH", label: "Bearish" },
];

const SECTORS = [
  "Communication Services",
  "Consumer Discretionary",
  "Consumer Staples",
  "Energy",
  "Financials",
  "Health Care",
  "Industrials",
  "Information Technology",
  "Materials",
  "Real Estate",
  "Utilities",
];

export interface FilterValues {
  index: string | null;
  rsiState: string | null;
  macdState: string | null;
  sector: string | null;
  scoreMin: number;
  scoreMax: number;
}

interface ScreenerFiltersProps {
  filters: FilterValues;
  onChange: (filters: FilterValues) => void;
  indexes: IndexResponse[];
}

export function ScreenerFilters({
  filters,
  onChange,
  indexes,
}: ScreenerFiltersProps) {
  function update(partial: Partial<FilterValues>) {
    onChange({ ...filters, ...partial });
  }

  function reset() {
    onChange({
      index: null,
      rsiState: null,
      macdState: null,
      sector: null,
      scoreMin: 0,
      scoreMax: 10,
    });
  }

  return (
    <div className="flex flex-wrap items-end gap-3">
      <Select
        value={filters.index ?? "__all__"}
        onValueChange={(v) => update({ index: v === "__all__" ? null : v })}
      >
        <SelectTrigger size="sm" className="min-w-[140px]">
          <SelectValue placeholder="Index: All" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__all__">All Indexes</SelectItem>
          {indexes.map((idx) => (
            <SelectItem key={idx.slug} value={idx.slug}>
              {idx.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={filters.rsiState ?? "__all__"}
        onValueChange={(v) =>
          update({ rsiState: v === "__all__" ? null : v })
        }
      >
        <SelectTrigger size="sm" className="min-w-[140px]">
          <SelectValue placeholder="RSI: All" />
        </SelectTrigger>
        <SelectContent>
          {RSI_OPTIONS.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={filters.macdState ?? "__all__"}
        onValueChange={(v) =>
          update({ macdState: v === "__all__" ? null : v })
        }
      >
        <SelectTrigger size="sm" className="min-w-[140px]">
          <SelectValue placeholder="MACD: All" />
        </SelectTrigger>
        <SelectContent>
          {MACD_OPTIONS.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={filters.sector ?? "__all__"}
        onValueChange={(v) =>
          update({ sector: v === "__all__" ? null : v })
        }
      >
        <SelectTrigger size="sm" className="min-w-[140px]">
          <SelectValue placeholder="Sector: All" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__all__">All Sectors</SelectItem>
          {SECTORS.map((s) => (
            <SelectItem key={s} value={s}>
              {s}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <div className="flex min-w-[200px] flex-col gap-1">
        <span className="text-xs text-muted-foreground">
          Score: {filters.scoreMin}–{filters.scoreMax}
        </span>
        <Slider
          value={[filters.scoreMin, filters.scoreMax]}
          min={0}
          max={10}
          step={0.5}
          onValueChange={(value) => {
            const arr = Array.isArray(value) ? value : [value];
            update({ scoreMin: arr[0], scoreMax: arr[1] ?? arr[0] });
          }}
        />
      </div>

      <Button variant="ghost" size="sm" onClick={reset}>
        Reset
      </Button>
    </div>
  );
}
