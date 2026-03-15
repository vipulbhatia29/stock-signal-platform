import React from "react";
import { render } from "@testing-library/react";
import { ChatPanel } from "@/components/chat-panel";

// Mock lucide-react to avoid SVG rendering issues in jsdom
jest.mock("lucide-react", () => ({
  SendIcon: () => <svg data-testid="send-icon" />,
  XIcon: () => <svg data-testid="x-icon" />,
}));

test("has translateX(100%) transform when closed", () => {
  const { container } = render(<ChatPanel isOpen={false} onClose={jest.fn()} />);
  const aside = container.querySelector("aside");
  expect(aside?.style.transform).toBe("translateX(100%)");
});

test("has translateX(0) transform when open", () => {
  const { container } = render(<ChatPanel isOpen={true} onClose={jest.fn()} />);
  const aside = container.querySelector("aside");
  expect(aside?.style.transform).toBe("translateX(0)");
});
