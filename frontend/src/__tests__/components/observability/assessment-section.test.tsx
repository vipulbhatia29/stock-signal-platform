import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AssessmentSection } from "@/app/(authenticated)/observability/_components/assessment-section";
import * as obsHooks from "@/hooks/use-observability";
import React from "react";

jest.mock("@/hooks/use-observability");

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(React.createElement(QueryClientProvider, { client: qc }, ui));
}

const mockLatest = {
  id: "r1",
  trigger: "weekly_ci",
  total_queries: 20,
  passed_queries: 17,
  pass_rate: 0.85,
  total_cost_usd: 0.12,
  started_at: "2026-03-30T00:00:00Z",
  completed_at: "2026-03-30T00:05:00Z",
};

describe("AssessmentSection", () => {
  it("renders pass rate from latest assessment", () => {
    (obsHooks.useAssessmentLatest as jest.Mock).mockReturnValue({ data: mockLatest, isLoading: false });
    (obsHooks.useAssessmentHistory as jest.Mock).mockReturnValue({ data: undefined, isLoading: false });
    wrap(<AssessmentSection isAdmin={false} />);
    expect(screen.getByText("85.0%")).toBeInTheDocument();
    expect(screen.getByText("Queries Tested")).toBeInTheDocument();
    expect(screen.getByText("20")).toBeInTheDocument();
  });

  it("shows coming soon when no data", () => {
    (obsHooks.useAssessmentLatest as jest.Mock).mockReturnValue({ data: null, isLoading: false });
    (obsHooks.useAssessmentHistory as jest.Mock).mockReturnValue({ data: undefined, isLoading: false });
    wrap(<AssessmentSection isAdmin={false} />);
    expect(screen.getByText(/Quality benchmarks coming soon/)).toBeInTheDocument();
  });

  it("hides history table for non-admin", () => {
    (obsHooks.useAssessmentLatest as jest.Mock).mockReturnValue({ data: mockLatest, isLoading: false });
    (obsHooks.useAssessmentHistory as jest.Mock).mockReturnValue({ data: undefined, isLoading: false });
    wrap(<AssessmentSection isAdmin={false} />);
    expect(screen.queryByText("Assessment History")).not.toBeInTheDocument();
  });

  it("shows history table for admin", () => {
    (obsHooks.useAssessmentLatest as jest.Mock).mockReturnValue({ data: mockLatest, isLoading: false });
    (obsHooks.useAssessmentHistory as jest.Mock).mockReturnValue({
      data: { items: [mockLatest] },
      isLoading: false,
    });
    wrap(<AssessmentSection isAdmin={true} />);
    expect(screen.getByText("Assessment History")).toBeInTheDocument();
  });
});
