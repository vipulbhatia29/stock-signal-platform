import { render, screen } from "@testing-library/react";
import { PlanDisplay } from "@/components/chat/plan-display";

describe("PlanDisplay", () => {
  it("renders steps with reasoning", () => {
    render(
      <PlanDisplay
        steps={["get_fundamentals", "get_analyst_targets"]}
        reasoning="Analyzing PLTR fundamentals"
        toolCalls={[]}
      />
    );
    expect(screen.getByText("Researching...")).toBeInTheDocument();
    expect(screen.getByText("Analyzing PLTR fundamentals")).toBeInTheDocument();
    expect(screen.getByText("get_fundamentals")).toBeInTheDocument();
    expect(screen.getByText("get_analyst_targets")).toBeInTheDocument();
  });

  it("shows checkmarks for completed tools", () => {
    render(
      <PlanDisplay
        steps={["get_fundamentals", "get_analyst_targets"]}
        reasoning=""
        toolCalls={[
          { id: "1", tool: "get_fundamentals", params: {}, status: "completed" },
        ]}
      />
    );
    const items = screen.getAllByRole("listitem");
    expect(items[0].textContent).toContain("✓");
    expect(items[1].textContent).toContain("○");
  });
});
