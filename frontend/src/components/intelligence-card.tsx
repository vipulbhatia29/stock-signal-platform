"use client";

import { CalendarIcon, TrendingDownIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { SectionHeading } from "@/components/section-heading";
import { CollapsibleSection } from "@/components/collapsible-section";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/error-state";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDate, formatCurrency, formatVolume } from "@/lib/format";
import type { StockIntelligenceResponse } from "@/types/api";

interface IntelligenceCardProps {
  intelligence: StockIntelligenceResponse | undefined;
  isLoading: boolean;
  isError?: boolean;
  onRetry?: () => void;
}

export function IntelligenceCard({
  intelligence,
  isLoading,
  isError,
  onRetry,
}: IntelligenceCardProps) {
  if (isLoading) {
    return (
      <div className="space-y-4">
        <SectionHeading>Intelligence</SectionHeading>
        <div className="grid grid-cols-2 gap-3">
          {[1, 2].map((i) => (
            <Skeleton key={i} className="h-16 rounded-lg" />
          ))}
        </div>
        <Skeleton className="h-12 rounded-lg" />
        <Skeleton className="h-12 rounded-lg" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="space-y-4">
        <SectionHeading>Intelligence</SectionHeading>
        <ErrorState error="Failed to load intelligence data" onRetry={onRetry} />
      </div>
    );
  }

  if (!intelligence) return null;

  const { upgrades_downgrades, insider_transactions, short_interest, next_earnings_date } =
    intelligence;

  return (
    <div className="space-y-4">
      <SectionHeading>Intelligence</SectionHeading>

      {/* Summary row — always visible */}
      <div className="grid grid-cols-2 gap-3">
        <div className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2.5">
          <CalendarIcon className="size-4 text-subtle" />
          <div>
            <p className="text-[10px] uppercase tracking-wider text-subtle">
              Next Earnings
            </p>
            <p className="text-sm font-medium text-foreground">
              {next_earnings_date
                ? formatDate(next_earnings_date)
                : "No upcoming earnings"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2.5">
          <TrendingDownIcon className="size-4 text-subtle" />
          <div>
            <p className="text-[10px] uppercase tracking-wider text-subtle">
              Short Interest
            </p>
            <p className="text-sm font-medium text-foreground">
              {short_interest
                ? `${short_interest.short_percent_of_float.toFixed(2)}%`
                : "N/A"}
            </p>
          </div>
        </div>
      </div>

      {/* Collapsible sub-sections */}
      <CollapsibleSection
        title="Analyst Ratings"
        count={upgrades_downgrades.length}
      >
        {upgrades_downgrades.length === 0 ? (
          <p className="text-sm text-muted-foreground">No recent analyst activity.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Firm</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Grade</TableHead>
                <TableHead>Date</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {upgrades_downgrades.map((u, i) => (
                <TableRow key={`${u.firm}-${u.date}-${i}`}>
                  <TableCell className="font-medium">{u.firm}</TableCell>
                  <TableCell>{u.action}</TableCell>
                  <TableCell>
                    {u.from_grade ? `${u.from_grade} → ` : ""}
                    {u.to_grade}
                  </TableCell>
                  <TableCell className="text-subtle">{formatDate(u.date)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CollapsibleSection>

      <CollapsibleSection
        title="Insider Transactions"
        count={insider_transactions.length}
      >
        {insider_transactions.length === 0 ? (
          <p className="text-sm text-muted-foreground">No recent insider activity.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Type</TableHead>
                <TableHead className="text-right">Shares</TableHead>
                <TableHead className="text-right">Value</TableHead>
                <TableHead>Date</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {insider_transactions.map((t, i) => (
                <TableRow key={`${t.insider_name}-${t.date}-${i}`}>
                  <TableCell className="font-medium">{t.insider_name}</TableCell>
                  <TableCell>{t.transaction_type}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatVolume(t.shares)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {t.value ? formatCurrency(t.value) : "—"}
                  </TableCell>
                  <TableCell className="text-subtle">{formatDate(t.date)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CollapsibleSection>

      {short_interest && (short_interest.short_ratio || short_interest.shares_short) && (
        <div className="rounded-lg border border-border bg-card px-4 py-3">
          <p className="text-sm font-medium text-foreground mb-2">Short Interest Detail</p>
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <p className="text-subtle text-xs">% of Float</p>
              <p className="font-mono tabular-nums">{short_interest.short_percent_of_float.toFixed(2)}%</p>
            </div>
            {short_interest.short_ratio && (
              <div>
                <p className="text-subtle text-xs">Short Ratio</p>
                <p className="font-mono tabular-nums">{short_interest.short_ratio.toFixed(1)}</p>
              </div>
            )}
            {short_interest.shares_short && (
              <div>
                <p className="text-subtle text-xs">Shares Short</p>
                <p className="font-mono tabular-nums">{formatVolume(short_interest.shares_short)}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
