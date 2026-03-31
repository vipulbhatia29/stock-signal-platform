import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useCurrentUser } from "@/hooks/use-current-user";
import * as api from "@/lib/api";
import React from "react";

jest.mock("@/lib/api", () => ({
  get: jest.fn(),
}));

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return React.createElement(QueryClientProvider, { client: qc }, children);
}

describe("useCurrentUser", () => {
  it("returns user profile and isAdmin=false for regular user", async () => {
    (api.get as jest.Mock).mockResolvedValue({
      id: "u1",
      email: "test@example.com",
      role: "user",
      is_active: true,
    });
    const { result } = renderHook(() => useCurrentUser(), { wrapper });
    await waitFor(() => expect(result.current.user).not.toBeNull());
    expect(result.current.isAdmin).toBe(false);
    expect(result.current.user?.email).toBe("test@example.com");
  });

  it("returns isAdmin=true for admin user", async () => {
    (api.get as jest.Mock).mockResolvedValue({
      id: "u2",
      email: "admin@example.com",
      role: "admin",
      is_active: true,
    });
    const { result } = renderHook(() => useCurrentUser(), { wrapper });
    await waitFor(() => expect(result.current.isAdmin).toBe(true));
  });
});
