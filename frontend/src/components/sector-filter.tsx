"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface SectorFilterProps {
  sectors: string[];
  selected: string | null;
  onChange: (sector: string | null) => void;
}

export function SectorFilter({
  sectors,
  selected,
  onChange,
}: SectorFilterProps) {
  return (
    <Select
      value={selected ?? "__all__"}
      onValueChange={(val) =>
        onChange(val === "__all__" ? null : val)
      }
    >
      <SelectTrigger size="sm" className="w-[160px]">
        <SelectValue placeholder="All Sectors" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="__all__">All Sectors</SelectItem>
        {sectors.map((sector) => (
          <SelectItem key={sector} value={sector}>
            {sector}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
