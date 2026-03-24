import React from "react";
import { render, screen } from "@testing-library/react";
import { ChatPanel } from "@/components/chat-panel";

// Mock lucide-react to avoid SVG rendering issues in jsdom
jest.mock("lucide-react", () => ({
  SendIcon: () => <svg data-testid="send-icon" />,
  XIcon: () => <svg data-testid="x-icon" />,
  Sparkles: () => <svg data-testid="sparkles-icon" />,
  BarChart3: () => <svg data-testid="barchart-icon" />,
  Globe: () => <svg data-testid="globe-icon" />,
  Bot: () => <svg data-testid="bot-icon" />,
  MessageSquare: () => <svg data-testid="message-icon" />,
}));

// Mock the hooks
jest.mock("@/hooks/use-stream-chat", () => ({
  useStreamChat: () => ({
    messages: [],
    isStreaming: false,
    error: null,
    activeSessionId: null,
    agentType: "stock",
    sendMessage: jest.fn(),
    stopGeneration: jest.fn(),
    retry: jest.fn(),
    switchSession: jest.fn(),
    startNewSession: jest.fn(),
    clearError: jest.fn(),
    dispatch: jest.fn(),
  }),
}));

jest.mock("@/hooks/use-chat", () => ({
  useChatSessions: () => ({ data: [] }),
  useChatMessages: () => ({ data: [] }),
  useDeleteSession: () => ({ mutate: jest.fn() }),
}));

test("has zero width when closed", () => {
  const { container } = render(
    <ChatPanel isOpen={false} onClose={jest.fn()} onArtifact={jest.fn()} />
  );
  const aside = container.querySelector("aside");
  expect(aside?.style.width).toBe("0px");
});

test("has non-zero width when open", () => {
  const { container } = render(
    <ChatPanel isOpen={true} onClose={jest.fn()} onArtifact={jest.fn()} />
  );
  const aside = container.querySelector("aside");
  // When open, width is set to CSS var; when closed, it's "0px"
  expect(aside?.style.width).not.toBe("0px");
});

test("shows agent selector when no active session", () => {
  render(<ChatPanel isOpen={true} onClose={jest.fn()} onArtifact={jest.fn()} />);
  expect(screen.getByText(/Stock Analyst/)).toBeInTheDocument();
});
