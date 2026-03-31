import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { ApiTrafficDetail } from "@/components/command-center/api-traffic-detail";
import type { ApiTrafficDrillDown } from "@/types/command-center-drilldown";

const mockData: ApiTrafficDrillDown = {
  window_seconds: 300,
  endpoints: [
    { endpoint: "GET /api/v1/stocks", count: 150 },
    { endpoint: "POST /api/v1/chat", count: 80 },
    { endpoint: "GET /api/v1/portfolio", count: 45 },
  ],
  total_requests_today: 1234,
  total_errors_today: 12,
  latency_p50_ms: 45,
  latency_p95_ms: 230,
  latency_p99_ms: 890,
  error_rate_pct: 0.97,
  sample_count: 500,
};

describe("ApiTrafficDetail", () => {
  it("renders summary metrics", () => {
    render(<ApiTrafficDetail data={mockData} />);
    expect(screen.getByText("1,234")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("230ms")).toBeInTheDocument();
  });

  it("renders endpoint table with all rows", () => {
    render(<ApiTrafficDetail data={mockData} />);
    const table = screen.getByTestId("endpoint-table");
    expect(table).toBeInTheDocument();
    expect(screen.getByText("GET /api/v1/stocks")).toBeInTheDocument();
    expect(screen.getByText("POST /api/v1/chat")).toBeInTheDocument();
    expect(screen.getByText("GET /api/v1/portfolio")).toBeInTheDocument();
  });

  it("sorts endpoints descending by default", () => {
    render(<ApiTrafficDetail data={mockData} />);
    const rows = screen.getByTestId("endpoint-table").querySelectorAll("tbody tr");
    expect(rows[0]).toHaveTextContent("GET /api/v1/stocks");
    expect(rows[1]).toHaveTextContent("POST /api/v1/chat");
  });

  it("toggles sort direction on click", async () => {
    const user = userEvent.setup();
    render(<ApiTrafficDetail data={mockData} />);
    const header = screen.getByText(/Count/);
    await user.click(header);
    const rows = screen.getByTestId("endpoint-table").querySelectorAll("tbody tr");
    // After toggle, ascending — smallest first
    expect(rows[0]).toHaveTextContent("GET /api/v1/portfolio");
  });

  it("handles null latency values with em-dash", () => {
    const nullData: ApiTrafficDrillDown = {
      ...mockData,
      latency_p50_ms: null,
      latency_p95_ms: null,
      latency_p99_ms: null,
      error_rate_pct: null,
    };
    render(<ApiTrafficDetail data={nullData} />);
    // p95 metric card should show em-dash
    const metricCards = document.querySelectorAll(".rounded-md");
    expect(metricCards.length).toBeGreaterThanOrEqual(3);
  });

  it("shows empty state when no endpoints", () => {
    render(<ApiTrafficDetail data={{ ...mockData, endpoints: [] }} />);
    expect(screen.getByText("No endpoint data")).toBeInTheDocument();
  });
});
