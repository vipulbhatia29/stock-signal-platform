import { render, screen } from "@testing-library/react";
import { DeclineMessage } from "@/components/chat/decline-message";

describe("DeclineMessage", () => {
  it("renders the decline content", () => {
    render(
      <DeclineMessage content="I focus on financial analysis and portfolio management." />
    );
    expect(
      screen.getByText("I focus on financial analysis and portfolio management.")
    ).toBeInTheDocument();
  });

  it("renders the lock icon", () => {
    render(<DeclineMessage content="Out of scope" />);
    expect(screen.getByText("🔒")).toBeInTheDocument();
  });
});
