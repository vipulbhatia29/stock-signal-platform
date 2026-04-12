import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useIngestTicker } from "@/hooks/use-stocks";
import * as api from "@/lib/api";
import React from "react";

jest.mock("@/lib/api", () => ({
  get: jest.fn(),
  post: jest.fn(),
}));

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return React.createElement(QueryClientProvider, { client: qc }, children);
}

describe("useIngestTicker", () => {
  it("invalidates full query set on success", async () => {
    const mockResponse = {
      ticker: "AAPL",
      name: "Apple Inc",
      rows_fetched: 100,
      composite_score: 7.5,
      status: "ok",
    };
    (api.post as jest.Mock).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useIngestTicker(), { wrapper });

    const invalidateSpy = jest.spyOn(
      QueryClient.prototype,
      "invalidateQueries"
    );

    await act(async () => {
      await result.current.mutateAsync("AAPL");
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // Verify all expected query keys are invalidated
    const invalidatedKeys = invalidateSpy.mock.calls.map(
      (call) => (call[0] as { queryKey: string[] }).queryKey
    );

    const expectedTickerKeys = [
      ["signals", "AAPL"],
      ["prices", "AAPL"],
      ["fundamentals", "AAPL"],
      ["stock-news", "AAPL"],
      ["stock-intelligence", "AAPL"],
      ["forecast", "AAPL"],
      ["benchmark", "AAPL"],
      ["stock-analytics", "AAPL"],
      ["ingest-state", "AAPL"],
    ];
    const expectedGlobalKeys = [
      ["watchlist"],
      ["bulk-signals"],
      ["portfolio", "positions"],
    ];

    for (const key of [...expectedTickerKeys, ...expectedGlobalKeys]) {
      expect(invalidatedKeys).toContainEqual(key);
    }

    invalidateSpy.mockRestore();
  });
});
