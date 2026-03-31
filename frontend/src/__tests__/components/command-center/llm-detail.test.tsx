import { render, screen } from "@testing-library/react";
import React from "react";
import { LlmDetail } from "@/components/command-center/llm-detail";
import type { LlmDrillDown } from "@/types/command-center-drilldown";

const mockData: LlmDrillDown = {
  hours: 24,
  total_models: 2,
  models: [
    {
      model: "llama-3.3-70b",
      provider: "groq",
      call_count: 42,
      total_cost_usd: 0.0035,
      avg_latency_ms: 890,
      error_count: 1,
      total_prompt_tokens: 12500,
      total_completion_tokens: 4200,
    },
    {
      model: "claude-sonnet-4-20250514",
      provider: "anthropic",
      call_count: 10,
      total_cost_usd: 0.15,
      avg_latency_ms: 2400,
      error_count: 0,
      total_prompt_tokens: 50000,
      total_completion_tokens: 8000,
    },
  ],
  cascades: [
    {
      model: "llama-3.3-70b",
      error: "Rate limit exceeded",
      timestamp: "2026-03-31T12:00:00Z",
    },
    {
      model: "llama-3.3-70b",
      error: "Timeout after 30s",
      timestamp: "2026-03-31T11:30:00Z",
    },
  ],
};

describe("LlmDetail", () => {
  it("renders model table with all rows", () => {
    render(<LlmDetail data={mockData} />);
    const table = screen.getByTestId("model-table");
    expect(table).toBeInTheDocument();
    // llama appears in both model table and cascade log
    expect(screen.getAllByText("llama-3.3-70b").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("claude-sonnet-4-20250514")).toBeInTheDocument();
  });

  it("renders model count in heading", () => {
    render(<LlmDetail data={mockData} />);
    expect(screen.getByText("Model Breakdown (2)")).toBeInTheDocument();
  });

  it("renders cascade log entries", () => {
    render(<LlmDetail data={mockData} />);
    const log = screen.getByTestId("cascade-log");
    expect(log).toBeInTheDocument();
    expect(screen.getByText("Rate limit exceeded")).toBeInTheDocument();
    expect(screen.getByText("Timeout after 30s")).toBeInTheDocument();
  });

  it("shows cascade count in heading", () => {
    render(<LlmDetail data={mockData} />);
    expect(screen.getByText("Cascade Log (2)")).toBeInTheDocument();
  });

  it("shows empty state for cascades when none", () => {
    render(<LlmDetail data={{ ...mockData, cascades: [] }} />);
    expect(screen.getByText("No cascades recorded")).toBeInTheDocument();
  });

  it("shows empty state for models when none", () => {
    render(
      <LlmDetail data={{ ...mockData, models: [], total_models: 0 }} />,
    );
    expect(screen.getByText("No model data")).toBeInTheDocument();
  });

  it("formats cost correctly for small amounts", () => {
    render(<LlmDetail data={mockData} />);
    // groq cost 0.0035 should show as $0.0035
    expect(screen.getByText("$0.0035")).toBeInTheDocument();
    // anthropic cost 0.15 should show as $0.15
    expect(screen.getByText("$0.15")).toBeInTheDocument();
  });
});
