"use client";

import { MetricCard } from "@/components/metric-card";
import { SectionHeading } from "@/components/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatCurrency } from "@/lib/format";
import type { DividendSummary } from "@/types/api";

interface DividendCardProps {
  dividends: DividendSummary | undefined;
  isLoading: boolean;
}

export function DividendCard({ dividends, isLoading }: DividendCardProps) {
  if (isLoading) {
    return (
      <div className="space-y-4">
        <SectionHeading>Dividends</SectionHeading>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-20 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  if (!dividends || dividends.payment_count === 0) {
    return (
      <div className="space-y-4">
        <SectionHeading>Dividends</SectionHeading>
        <p className="text-sm text-muted-foreground">
          No dividend history available for this ticker.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <SectionHeading>Dividends</SectionHeading>

      {/* KPI metrics row */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricCard
          label="Dividend Yield"
          value={
            dividends.dividend_yield !== null
              ? `${dividends.dividend_yield.toFixed(2)}%`
              : "N/A"
          }
        />
        <MetricCard
          label="Annual Dividend"
          value={formatCurrency(dividends.annual_dividends)}
        />
        <MetricCard
          label="Total Received"
          value={formatCurrency(dividends.total_received)}
        />
        <MetricCard
          label="Payments"
          value={dividends.payment_count.toString()}
        />
      </div>

      {/* Payment history (collapsible) */}
      {dividends.history.length > 0 && (
        <details className="rounded-lg border">
          <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-muted-foreground hover:text-foreground">
            Payment history ({dividends.history.length})
          </summary>
          <div className="overflow-x-auto border-t">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Ex-Date</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {dividends.history.slice(0, 20).map((payment) => (
                  <TableRow key={payment.ex_date}>
                    <TableCell className="text-sm text-muted-foreground">
                      {new Date(payment.ex_date).toLocaleDateString()}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatCurrency(payment.amount)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {dividends.history.length > 20 && (
              <p className="px-4 py-2 text-xs text-muted-foreground">
                Showing 20 of {dividends.history.length} payments
              </p>
            )}
          </div>
        </details>
      )}
    </div>
  );
}
