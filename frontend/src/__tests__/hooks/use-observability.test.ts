import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  useObservabilityKPIs,
  useObservabilityQueries,
  useQueryDetail,
  useObservabilityGrouped,
  useAssessmentLatest,
} from "@/hooks/use-observability";
import * as api from "@/lib/api";
import React from "react";

jest.mock("@/lib/api", () => ({
  get: jest.fn(),
}));

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return React.createElement(QueryClientProvider, { client: qc }, children);
}

const mockGet = api.get as jest.Mock;

describe("useObservabilityKPIs", () => {
  it("fetches KPIs", async () => {
    mockGet.mockResolvedValue({
      queries_today: 42,
      avg_latency_ms: 1200,
      avg_cost_per_query: 0.003,
      pass_rate: 0.87,
      fallback_rate_pct: 0.02,
    });
    const { result } = renderHook(() => useObservabilityKPIs(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.queries_today).toBe(42);
    expect(mockGet).toHaveBeenCalledWith("/observability/kpis");
  });
});

describe("useObservabilityQueries", () => {
  it("passes query params", async () => {
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, size: 25 });
    const { result } = renderHook(
      () => useObservabilityQueries({ page: 2, status: "error" }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(mockGet).toHaveBeenCalledWith(expect.stringContaining("page=2"));
    expect(mockGet).toHaveBeenCalledWith(
      expect.stringContaining("status=error"),
    );
  });
});

describe("useQueryDetail", () => {
  it("does not fetch when queryId is null", () => {
    renderHook(() => useQueryDetail(null), { wrapper });
    expect(mockGet).not.toHaveBeenCalledWith(
      expect.stringContaining("/observability/queries/"),
    );
  });

  it("fetches when queryId is provided", async () => {
    mockGet.mockResolvedValue({
      query_id: "abc",
      query_text: "test",
      steps: [],
      langfuse_trace_url: null,
    });
    const { result } = renderHook(() => useQueryDetail("abc"), { wrapper });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(mockGet).toHaveBeenCalledWith("/observability/queries/abc");
  });
});

describe("useObservabilityGrouped", () => {
  it("sends group_by param", async () => {
    mockGet.mockResolvedValue({
      group_by: "date",
      bucket: "day",
      groups: [],
      total_queries: 0,
    });
    const { result } = renderHook(
      () => useObservabilityGrouped({ group_by: "date", bucket: "day" }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(mockGet).toHaveBeenCalledWith(
      expect.stringContaining("group_by=date"),
    );
  });
});

describe("useAssessmentLatest", () => {
  it("fetches latest assessment", async () => {
    mockGet.mockResolvedValue({
      id: "r1",
      pass_rate: 0.85,
      total_queries: 20,
    });
    const { result } = renderHook(() => useAssessmentLatest(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(mockGet).toHaveBeenCalledWith("/observability/assessment/latest");
  });
});
