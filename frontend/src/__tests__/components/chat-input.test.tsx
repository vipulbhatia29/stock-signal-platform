import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChatInput } from "@/components/chat/chat-input";

test("calls onSend when Enter is pressed", async () => {
  const onSend = jest.fn();
  render(<ChatInput onSend={onSend} onStop={jest.fn()} isStreaming={false} />);
  const textarea = screen.getByPlaceholderText(/Ask about/);
  await userEvent.type(textarea, "Analyze AAPL{enter}");
  expect(onSend).toHaveBeenCalledWith("Analyze AAPL");
});

test("does not send on Shift+Enter (newline)", async () => {
  const onSend = jest.fn();
  render(<ChatInput onSend={onSend} onStop={jest.fn()} isStreaming={false} />);
  const textarea = screen.getByPlaceholderText(/Ask about/);
  await userEvent.type(textarea, "line 1{shift>}{enter}{/shift}line 2");
  expect(onSend).not.toHaveBeenCalled();
});

test("shows stop button when streaming", () => {
  render(<ChatInput onSend={jest.fn()} onStop={jest.fn()} isStreaming={true} />);
  expect(screen.getByLabelText("Stop generation")).toBeInTheDocument();
});
