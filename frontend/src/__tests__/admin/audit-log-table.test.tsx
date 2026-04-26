import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuditLogTable } from "@/components/admin/audit-log-table";

// Mock the hook
jest.mock("@/hooks/use-admin-pipelines", () => ({
  useAuditLog: jest.fn(),
}));

import { useAuditLog } from "@/hooks/use-admin-pipelines";

const mockUseAuditLog = useAuditLog as jest.MockedFunction<typeof useAuditLog>;

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

const MOCK_ENTRIES = [
  {
    id: "1",
    user_id: "u1",
    action: "cache_clear",
    target: "signals:*",
    metadata: { keys_deleted: 42 },
    created_at: new Date().toISOString(),
  },
  {
    id: "2",
    user_id: "u1",
    action: "trigger_group",
    target: "nightly",
    metadata: null,
    created_at: new Date(Date.now() - 900_000).toISOString(),
  },
];

beforeEach(() => {
  mockUseAuditLog.mockReturnValue({
    data: { total: 127, limit: 50, offset: 0, entries: MOCK_ENTRIES },
    isLoading: false,
    error: null,
  } as ReturnType<typeof useAuditLog>);
});

test("renders table with audit entries", () => {
  render(<AuditLogTable />, { wrapper: Wrapper });
  expect(screen.getByText("cache_clear")).toBeInTheDocument();
  expect(screen.getByText("signals:*")).toBeInTheDocument();
  expect(screen.getByText("trigger_group")).toBeInTheDocument();
  expect(screen.getByText("nightly")).toBeInTheDocument();
});

test("shows pagination info", () => {
  render(<AuditLogTable />, { wrapper: Wrapper });
  expect(screen.getByText(/1-50 of 127/)).toBeInTheDocument();
});

test("prev button disabled on first page", () => {
  render(<AuditLogTable />, { wrapper: Wrapper });
  expect(screen.getByRole("button", { name: /prev/i })).toBeDisabled();
});

test("next button navigates to next page", () => {
  render(<AuditLogTable />, { wrapper: Wrapper });
  const nextBtn = screen.getByRole("button", { name: /next/i });
  expect(nextBtn).not.toBeDisabled();
  fireEvent.click(nextBtn);
  expect(mockUseAuditLog).toHaveBeenCalledWith(undefined, 50, 50);
});

test("renders empty state when no entries", () => {
  mockUseAuditLog.mockReturnValue({
    data: { total: 0, limit: 50, offset: 0, entries: [] },
    isLoading: false,
    error: null,
  } as ReturnType<typeof useAuditLog>);
  render(<AuditLogTable />, { wrapper: Wrapper });
  expect(screen.getByText(/no audit log entries/i)).toBeInTheDocument();
});

test("filter dropdown changes action filter", () => {
  render(<AuditLogTable />, { wrapper: Wrapper });
  const select = screen.getByRole("combobox");
  fireEvent.change(select, { target: { value: "cache_clear" } });
  expect(mockUseAuditLog).toHaveBeenCalledWith("cache_clear", 50, 0);
});
