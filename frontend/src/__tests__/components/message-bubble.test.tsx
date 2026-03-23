import { render, screen } from "@testing-library/react";
import { MessageBubble } from "@/components/chat/message-bubble";

test("renders user message right-aligned", () => {
  render(
    <MessageBubble
      role="user"
      content="Analyze AAPL"
      toolCalls={[]}
      isStreaming={false}
    />
  );
  expect(screen.getByText("Analyze AAPL")).toBeInTheDocument();
});

test("renders assistant message with markdown", () => {
  render(
    <MessageBubble
      role="assistant"
      content="**AAPL** looks strong"
      toolCalls={[]}
      isStreaming={false}
    />
  );
  expect(screen.getByText("**AAPL** looks strong")).toBeInTheDocument();
});

test("renders tool cards for assistant messages", () => {
  render(
    <MessageBubble
      role="assistant"
      content="Analysis complete"
      toolCalls={[
        { id: "1", tool: "analyze_stock", params: { ticker: "AAPL" }, status: "completed", result: {} },
      ]}
      isStreaming={false}
    />
  );
  expect(screen.getByText("analyze_stock")).toBeInTheDocument();
});
