import { render, screen } from "@testing-library/react";
import { SessionList } from "@/components/chat/session-list";

const mockSessions = [
  { id: "1", title: "Analyze AAPL", agent_type: "stock" as const, is_active: true, created_at: "2026-03-19T10:00:00Z", last_active_at: "2026-03-19T10:00:00Z" },
  { id: "2", title: "News search", agent_type: "general" as const, is_active: false, created_at: "2026-03-18T10:00:00Z", last_active_at: "2026-03-18T10:00:00Z" },
];

test("renders session titles", () => {
  render(
    <SessionList sessions={mockSessions} activeId="1" onSwitch={jest.fn()} onDelete={jest.fn()} onNew={jest.fn()} />
  );
  expect(screen.getByText("Analyze AAPL")).toBeInTheDocument();
  expect(screen.getByText("News search")).toBeInTheDocument();
});

test("shows expired badge for inactive sessions", () => {
  render(
    <SessionList sessions={mockSessions} activeId="1" onSwitch={jest.fn()} onDelete={jest.fn()} onNew={jest.fn()} />
  );
  expect(screen.getByText("Expired")).toBeInTheDocument();
});
