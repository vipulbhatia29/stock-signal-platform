import { render, screen, fireEvent } from "@testing-library/react";
import { EvidenceSection } from "@/components/chat/evidence-section";

describe("EvidenceSection", () => {
  const evidence = [
    { claim: "Score 8.2", source_tool: "analyze_stock", value: "8.2" },
    { claim: "Revenue growth 21%", source_tool: "get_fundamentals", value: "0.21" },
  ];

  it("renders collapsed by default", () => {
    render(<EvidenceSection evidence={evidence} />);
    expect(screen.getByText(/Show Evidence/)).toBeInTheDocument();
    expect(screen.queryByText("Score 8.2")).not.toBeInTheDocument();
  });

  it("expands on click to show evidence items", () => {
    render(<EvidenceSection evidence={evidence} />);
    fireEvent.click(screen.getByText(/Show Evidence/));
    expect(screen.getByText("Score 8.2")).toBeInTheDocument();
    expect(screen.getByText("[analyze_stock]")).toBeInTheDocument();
  });

  it("returns null for empty evidence", () => {
    const { container } = render(<EvidenceSection evidence={[]} />);
    expect(container.firstChild).toBeNull();
  });
});
