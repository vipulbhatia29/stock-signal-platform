"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { postMultipart } from "@/lib/api";
import type { BulkTransactionResponse } from "@/types/api";

export function useBulkUploadTransactions() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, validateOnly }: { file: File; validateOnly: boolean }) => {
      const formData = new FormData();
      formData.append("file", file);
      return postMultipart<BulkTransactionResponse>(
        `/portfolio/transactions/bulk?validate_only=${validateOnly}`,
        formData
      );
    },
    onSuccess: (_data, variables) => {
      if (!variables.validateOnly) {
        queryClient.invalidateQueries({ queryKey: ["portfolio"] });
        queryClient.invalidateQueries({ queryKey: ["stocks"] });
        queryClient.invalidateQueries({ queryKey: ["watchlist"] });
      }
    },
  });
}
