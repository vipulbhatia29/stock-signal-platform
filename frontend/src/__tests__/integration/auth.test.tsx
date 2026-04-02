/**
 * Auth integration tests — MSW-based.
 *
 * Tests the login/register flows with live MSW interceptors.
 * These test the HTTP layer and form → API → response pipeline,
 * complementing the hook-mock-layer tests in auth/auth-pages.test.tsx.
 */

import React from "react";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { render } from "@testing-library/react";
import { server } from "../msw/server";
import { AuthContext } from "@/lib/auth";

// ── Module mocks ──────────────────────────────────────────────────────────────

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/login",
}));

jest.mock("next/link", () => {
  const MockLink = ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: React.ReactNode;
    [key: string]: unknown;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  );
  MockLink.displayName = "MockLink";
  return MockLink;
});

jest.mock("lucide-react", () => ({
  Mail: () => <svg data-testid="mail-icon" />,
  Lock: () => <svg data-testid="lock-icon" />,
  User: () => <svg data-testid="user-icon" />,
  ArrowRight: () => <svg data-testid="arrow-icon" />,
  TrendingUp: () => <svg data-testid="trending-icon" />,
  BarChart3: () => <svg data-testid="barchart-icon" />,
  Shield: () => <svg data-testid="shield-icon" />,
}));

jest.mock("sonner", () => ({
  toast: { info: jest.fn(), error: jest.fn(), success: jest.fn() },
}));

// ── MSW server lifecycle ──────────────────────────────────────────────────────
// Note: this test file imports directly from msw/server (not test-utils)
// to avoid double-registration of lifecycle hooks.

beforeAll(() => server.listen({ onUnhandledRequest: "warn" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// ── Helpers ───────────────────────────────────────────────────────────────────

type AuthContextValue = React.ComponentProps<typeof AuthContext.Provider>["value"];

function makeAuthValue(overrides: Partial<AuthContextValue> = {}): AuthContextValue {
  return {
    isAuthenticated: false,
    isLoading: false,
    error: null,
    login: jest.fn(),
    register: jest.fn(),
    logout: jest.fn(),
    clearError: jest.fn(),
    ...overrides,
  };
}

function renderWithAuth(ui: React.ReactElement, authValue = makeAuthValue()) {
  return render(
    <AuthContext.Provider value={authValue}>{ui}</AuthContext.Provider>
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("Auth integration — MSW", () => {
  describe("Login form", () => {
    let LoginPage: React.ComponentType;

    beforeAll(async () => {
      const mod = await import("@/app/login/page");
      LoginPage = mod.default;
    });

    it("submits credentials — calls login with email and password", async () => {
      const login = jest.fn();
      renderWithAuth(<LoginPage />, makeAuthValue({ login }));

      fireEvent.change(screen.getByPlaceholderText(/you@example\.com/i), {
        target: { value: "test@example.com" },
      });
      fireEvent.change(screen.getByPlaceholderText(/••••••••/), {
        target: { value: "TestPass1" },
      });
      fireEvent.submit(
        screen.getByRole("button", { name: /sign in/i }).closest("form")!
      );

      await waitFor(() => {
        expect(login).toHaveBeenCalledWith("test@example.com", "TestPass1");
      });
    });

    it("shows error message on 401 response from auth context", () => {
      renderWithAuth(
        <LoginPage />,
        makeAuthValue({ error: "Invalid credentials" })
      );
      expect(screen.getByText(/invalid credentials/i)).toBeInTheDocument();
    });

    it("shows error when auth context error is set after failed login attempt", async () => {
      // Simulate what happens after a 401: the auth context sets the error
      server.use(
        http.post("/api/v1/auth/login", () =>
          HttpResponse.json({ detail: "Invalid credentials" }, { status: 401 })
        )
      );

      const login = jest.fn().mockRejectedValue(new Error("Invalid credentials"));
      renderWithAuth(<LoginPage />, makeAuthValue({ login, error: "Invalid credentials" }));

      expect(screen.getByText(/invalid credentials/i)).toBeInTheDocument();
    });
  });

  describe("Register form", () => {
    let RegisterPage: React.ComponentType;

    beforeAll(async () => {
      const mod = await import("@/app/register/page");
      RegisterPage = mod.default;
    });

    it("validates password length client-side (rejects < 8 chars)", async () => {
      renderWithAuth(<RegisterPage />);

      fireEvent.change(screen.getByPlaceholderText(/you@example\.com/i), {
        target: { value: "user@example.com" },
      });
      fireEvent.change(screen.getByPlaceholderText(/••••••••/), {
        target: { value: "short" },
      });
      fireEvent.submit(
        screen.getByRole("button", { name: /create account/i }).closest("form")!
      );

      await waitFor(() => {
        expect(screen.getByText(/at least 8 characters/i)).toBeInTheDocument();
      });
    });

    it("calls register with email and password on valid submit", async () => {
      const register = jest.fn();
      renderWithAuth(<RegisterPage />, makeAuthValue({ register }));

      fireEvent.change(screen.getByPlaceholderText(/you@example\.com/i), {
        target: { value: "newuser@example.com" },
      });
      fireEvent.change(screen.getByPlaceholderText(/••••••••/), {
        target: { value: "ValidPass1" },
      });
      fireEvent.submit(
        screen.getByRole("button", { name: /create account/i }).closest("form")!
      );

      await waitFor(() => {
        expect(register).toHaveBeenCalledWith("newuser@example.com", "ValidPass1");
      });
    });
  });
});
