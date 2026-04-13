"use client";

import { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { useBulkUploadTransactions } from "@/hooks/use-bulk-transactions";
import { toast } from "sonner";
import type { BulkTransactionResponse } from "@/types/api";

export function BulkTransactionUpload({ onClose }: { onClose: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<BulkTransactionResponse | null>(null);
  const upload = useBulkUploadTransactions();

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f && f.type !== "text/csv" && !f.name.endsWith(".csv")) {
      toast.error("Please select a CSV file");
      return;
    }
    setFile(f ?? null);
    setResult(null);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f && !f.name.endsWith(".csv")) {
      toast.error("Please drop a CSV file");
      return;
    }
    setFile(f ?? null);
    setResult(null);
  }, []);

  const handleSubmit = useCallback(async (validateOnly: boolean) => {
    if (!file) return;
    try {
      const res = await upload.mutateAsync({ file, validateOnly });
      setResult(res);
      if (!validateOnly && res.errors.length === 0) {
        toast.success(`${res.created} transactions imported`);
        onClose();
      }
    } catch {
      toast.error("Upload failed");
    }
  }, [file, upload, onClose]);

  return (
    <div className="space-y-4">
      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={handleDrop}
        className="rounded-lg border-2 border-dashed border-muted-foreground/25 p-8 text-center"
      >
        <p className="text-sm text-muted-foreground">
          Drag & drop a CSV file, or{" "}
          <label className="cursor-pointer text-blue-400 underline">
            browse
            <input
              type="file"
              accept=".csv"
              onChange={handleFileChange}
              className="hidden"
            />
          </label>
        </p>
        {file && <p className="mt-2 text-sm font-medium">{file.name}</p>}
      </div>

      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={!file || upload.isPending}
          onClick={() => handleSubmit(true)}
        >
          Validate
        </Button>
        <Button
          size="sm"
          disabled={!file || upload.isPending}
          onClick={() => handleSubmit(false)}
        >
          {upload.isPending ? "Uploading\u2026" : "Upload"}
        </Button>
      </div>

      {result && (
        <div className="space-y-2 text-sm">
          {result.validate_only && (
            <p className="text-blue-400">
              Validation: {result.created} rows valid, {result.errors.length} errors
            </p>
          )}
          {!result.validate_only && result.created > 0 && (
            <p className="text-green-400">{result.created} transactions created</p>
          )}
          {result.skipped > 0 && (
            <p className="text-amber-400">{result.skipped} rows skipped</p>
          )}
          {result.errors.length > 0 && (
            <div className="max-h-40 overflow-y-auto rounded bg-red-500/10 p-2">
              {result.errors.map((err, i) => (
                <p key={i} className="text-xs text-red-400">
                  Row {err.row}{err.ticker ? ` (${err.ticker})` : ""}: {err.error}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
