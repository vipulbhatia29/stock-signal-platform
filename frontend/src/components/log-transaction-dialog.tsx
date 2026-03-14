"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PlusIcon } from "lucide-react";
import type { TransactionCreate } from "@/types/api";

interface LogTransactionDialogProps {
  onSubmit: (data: TransactionCreate) => void;
  isLoading: boolean;
}

export function LogTransactionDialog({
  onSubmit,
  isLoading,
}: LogTransactionDialogProps) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<TransactionCreate>({
    ticker: "",
    transaction_type: "BUY",
    shares: "",
    price_per_share: "",
    transacted_at: new Date().toISOString().split("T")[0] + "T00:00:00Z",
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSubmit(form);
    setOpen(false);
    setForm({
      ticker: "",
      transaction_type: "BUY",
      shares: "",
      price_per_share: "",
      transacted_at: new Date().toISOString().split("T")[0] + "T00:00:00Z",
    });
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" />}>
        <PlusIcon className="mr-2 size-4" />
        Log Transaction
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Log Transaction</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="ticker">Ticker</Label>
            <Input
              id="ticker"
              placeholder="AAPL"
              value={form.ticker}
              onChange={(e) =>
                setForm({ ...form, ticker: e.target.value.toUpperCase() })
              }
              required
              maxLength={10}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="type">Type</Label>
            <Select
              value={form.transaction_type}
              onValueChange={(v) =>
                setForm({
                  ...form,
                  transaction_type: (v ?? "BUY") as "BUY" | "SELL",
                })
              }
            >
              <SelectTrigger id="type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="BUY">BUY</SelectItem>
                <SelectItem value="SELL">SELL</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="shares">Shares</Label>
              <Input
                id="shares"
                type="number"
                placeholder="10"
                step="0.0001"
                min="0.0001"
                value={form.shares}
                onChange={(e) => setForm({ ...form, shares: e.target.value })}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="price">Price / Share</Label>
              <Input
                id="price"
                type="number"
                placeholder="182.50"
                step="0.0001"
                min="0.0001"
                value={form.price_per_share}
                onChange={(e) =>
                  setForm({ ...form, price_per_share: e.target.value })
                }
                required
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="date">Date</Label>
            <Input
              id="date"
              type="date"
              value={form.transacted_at.split("T")[0]}
              onChange={(e) =>
                setForm({
                  ...form,
                  transacted_at: e.target.value + "T00:00:00Z",
                })
              }
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="notes">Notes (optional)</Label>
            <Input
              id="notes"
              placeholder="e.g. Earnings dip buy"
              value={form.notes ?? ""}
              onChange={(e) =>
                setForm({ ...form, notes: e.target.value || undefined })
              }
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isLoading}>
              {isLoading ? "Saving…" : "Log Trade"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
