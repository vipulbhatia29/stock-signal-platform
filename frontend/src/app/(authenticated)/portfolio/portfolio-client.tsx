"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { get, post, del } from "@/lib/api";
import { useRebalancing } from "@/hooks/use-stocks";
import { toast } from "sonner";
import { Trash2Icon } from "lucide-react";
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { SectionHeading } from "@/components/section-heading";
import { MetricCard } from "@/components/metric-card";
import { ChangeIndicator } from "@/components/change-indicator";
import { Badge } from "@/components/ui/badge";
import { LogTransactionDialog } from "@/components/log-transaction-dialog";
import { PortfolioValueChart } from "@/components/portfolio-value-chart";
import { PortfolioSettingsSheet } from "@/components/portfolio-settings-sheet";
import { RebalancingPanel } from "@/components/rebalancing-panel";
import { formatCurrency, formatNumber } from "@/lib/format";
import type {
  DivestmentAlert,
  Position,
  PortfolioSnapshot,
  PortfolioSummary,
  Transaction,
  TransactionCreate,
} from "@/types/api";

// ── Data hooks ────────────────────────────────────────────────────────────────

function usePositions() {
  return useQuery<Position[]>({
    queryKey: ["portfolio", "positions"],
    queryFn: () => get<Position[]>("/portfolio/positions"),
    staleTime: 60 * 1000,
  });
}

function usePortfolioSummary() {
  return useQuery<PortfolioSummary>({
    queryKey: ["portfolio", "summary"],
    queryFn: () => get<PortfolioSummary>("/portfolio/summary"),
    staleTime: 60 * 1000,
  });
}

function useTransactions() {
  return useQuery<Transaction[]>({
    queryKey: ["portfolio", "transactions"],
    queryFn: () => get<Transaction[]>("/portfolio/transactions"),
    staleTime: 60 * 1000,
  });
}

function usePortfolioHistory(days = 365) {
  return useQuery<PortfolioSnapshot[]>({
    queryKey: ["portfolio", "history", days],
    queryFn: () =>
      get<PortfolioSnapshot[]>(`/portfolio/history?days=${days}`),
    staleTime: 15 * 60 * 1000,
  });
}

function useLogTransaction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: TransactionCreate) =>
      post<Transaction>("/portfolio/transactions", data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolio"] });
      toast.success("Transaction logged");
    },
    onError: (err: Error) => {
      toast.error(err.message || "Failed to log transaction");
    },
  });
}

function useDeleteTransaction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => del<void>(`/portfolio/transactions/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolio"] });
      toast.success("Transaction deleted");
    },
    onError: (err: Error) => {
      toast.error(err.message || "Cannot delete transaction");
    },
  });
}

// ── Sector pie colours (cycle through chart palette) ─────────────────────────

const SECTOR_COLORS = [
  "#6366f1",
  "#f59e0b",
  "#10b981",
  "#ef4444",
  "#3b82f6",
  "#8b5cf6",
  "#ec4899",
  "#14b8a6",
];

// ── Sub-components ────────────────────────────────────────────────────────────

function KpiRow({ summary }: { summary: PortfolioSummary }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <MetricCard
        label="Total Value"
        value={formatCurrency(summary.total_value)}
      />
      <MetricCard
        label="Cost Basis"
        value={formatCurrency(summary.total_cost_basis)}
      />
      <MetricCard
        label="Unrealized P&L"
        value={formatCurrency(summary.unrealized_pnl)}
        change={summary.unrealized_pnl}
        formatChange="currency"
      />
      <MetricCard
        label="Return"
        value={`${summary.unrealized_pnl_pct >= 0 ? "+" : ""}${summary.unrealized_pnl_pct.toFixed(2)}%`}
        change={summary.unrealized_pnl_pct}
        formatChange="percent"
      />
    </div>
  );
}

function PositionsTable({
  positions,
  onDelete,
  isDeleting,
}: {
  positions: Position[];
  onDelete: (ticker: string) => void;
  isDeleting: boolean;
}) {
  const { data: transactions } = useTransactions();

  if (positions.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        No open positions. Log a BUY transaction to get started.
      </p>
    );
  }

  return (
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Ticker</TableHead>
            <TableHead className="text-right">Shares</TableHead>
            <TableHead className="text-right">Avg Cost</TableHead>
            <TableHead className="text-right">Price</TableHead>
            <TableHead className="text-right">Market Value</TableHead>
            <TableHead className="text-right">Unrealized P&L</TableHead>
            <TableHead className="text-right">Return</TableHead>
            <TableHead className="text-right">Weight</TableHead>
            <TableHead>Alerts</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {positions.map((pos) => (
            <TableRow key={pos.ticker}>
              <TableCell className="font-semibold">{pos.ticker}</TableCell>
              <TableCell className="text-right tabular-nums">
                {formatNumber(pos.shares, 4)}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {formatCurrency(pos.avg_cost_basis)}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {pos.current_price !== null
                  ? formatCurrency(pos.current_price)
                  : "—"}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {pos.market_value !== null
                  ? formatCurrency(pos.market_value)
                  : "—"}
              </TableCell>
              <TableCell className="text-right">
                <ChangeIndicator
                  value={pos.unrealized_pnl}
                  format="currency"
                  size="sm"
                />
              </TableCell>
              <TableCell className="text-right">
                <ChangeIndicator
                  value={pos.unrealized_pnl_pct}
                  format="percent"
                  size="sm"
                />
              </TableCell>
              <TableCell className="text-right tabular-nums text-muted-foreground text-sm">
                {pos.allocation_pct !== null
                  ? `${pos.allocation_pct.toFixed(1)}%`
                  : "—"}
              </TableCell>
              <TableCell>
                <AlertBadges alerts={pos.alerts} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {transactions && transactions.length > 0 && (
        <details className="border-t">
          <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-muted-foreground hover:text-foreground">
            Transaction history ({transactions.length})
          </summary>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Ticker</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead className="text-right">Shares</TableHead>
                  <TableHead className="text-right">Price</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {transactions.map((txn) => (
                  <TableRow key={txn.id}>
                    <TableCell className="text-sm text-muted-foreground">
                      {new Date(txn.transacted_at).toLocaleDateString()}
                    </TableCell>
                    <TableCell className="font-medium">{txn.ticker}</TableCell>
                    <TableCell>
                      <span
                        className={
                          txn.transaction_type === "BUY"
                            ? "text-gain font-medium"
                            : "text-loss font-medium"
                        }
                      >
                        {txn.transaction_type}
                      </span>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatNumber(txn.shares, 4)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatCurrency(txn.price_per_share)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatCurrency(txn.shares * txn.price_per_share)}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-7 text-muted-foreground hover:text-destructive"
                        disabled={isDeleting}
                        onClick={() => onDelete(txn.id)}
                        aria-label={`Delete ${txn.ticker} transaction`}
                      >
                        <Trash2Icon className="size-3.5" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </details>
      )}
    </div>
  );
}

function AllocationPie({ sectors }: { summary: PortfolioSummary; sectors: PortfolioSummary["sectors"] }) {
  if (sectors.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
        No sector data yet
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <PieChart>
        <Pie
          data={sectors}
          dataKey="market_value"
          nameKey="sector"
          cx="50%"
          cy="50%"
          outerRadius={90}
          strokeWidth={1}
        >
          {sectors.map((entry, index) => (
            <Cell
              key={entry.sector}
              fill={SECTOR_COLORS[index % SECTOR_COLORS.length]}
              stroke={entry.over_limit ? "#ef4444" : "transparent"}
              strokeWidth={entry.over_limit ? 2 : 0}
            />
          ))}
        </Pie>
        <Tooltip
          formatter={(value, name) => [
            formatCurrency(typeof value === "number" ? value : null),
            name as string,
          ]}
        />
        <Legend
          formatter={(value, entry) => {
            const payload = entry.payload as { pct?: number; over_limit?: boolean } | undefined;
            const pct = payload?.pct ?? 0;
            const over = payload?.over_limit ?? false;
            return (
              <span className={over ? "font-semibold text-destructive" : ""}>
                {value} ({pct.toFixed(1)}%)
                {over ? " ⚠" : ""}
              </span>
            );
          }}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}

function AlertBadges({ alerts }: { alerts: DivestmentAlert[] }) {
  if (!alerts || alerts.length === 0) return null;

  return (
    <div className="flex flex-col gap-1">
      {alerts.map((alert) => (
        <Badge
          key={alert.rule}
          variant="outline"
          className={
            alert.severity === "critical"
              ? "bg-red-500/10 text-loss border-red-500/20 text-xs"
              : "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/20 text-xs"
          }
        >
          {alert.message}
        </Badge>
      ))}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function PortfolioClient() {
  const { data: summary } = usePortfolioSummary();
  const { data: positions } = usePositions();
  const { data: history } = usePortfolioHistory();
  const { data: rebalancing } = useRebalancing();
  const logTransaction = useLogTransaction();
  const deleteTransaction = useDeleteTransaction();

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-6">
      <div className="flex items-center justify-between">
        <SectionHeading>Portfolio</SectionHeading>
        <div className="flex items-center gap-2">
          <PortfolioSettingsSheet />
          <LogTransactionDialog
            onSubmit={(data) => logTransaction.mutate(data)}
            isLoading={logTransaction.isPending}
          />
        </div>
      </div>

      {/* KPI row */}
      {summary && <KpiRow summary={summary} />}

      {/* Value history chart */}
      <div className="space-y-3">
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
          Value History
        </h2>
        <div className="rounded-lg border p-4">
          <PortfolioValueChart snapshots={history ?? []} />
        </div>
      </div>

      {/* Positions + allocation */}
      <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
        {/* Positions table */}
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
            Positions
          </h2>
          <PositionsTable
            positions={positions ?? []}
            onDelete={(id) => deleteTransaction.mutate(id)}
            isDeleting={deleteTransaction.isPending}
          />
        </div>

        {/* Sector allocation */}
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
            Sector Allocation
          </h2>
          <div className="rounded-lg border p-4">
            {summary ? (
              <AllocationPie summary={summary} sectors={summary.sectors} />
            ) : (
              <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
                Loading…
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Rebalancing suggestions */}
      {rebalancing && rebalancing.suggestions.length > 0 && (
        <RebalancingPanel suggestions={rebalancing.suggestions} />
      )}
    </div>
  );
}
