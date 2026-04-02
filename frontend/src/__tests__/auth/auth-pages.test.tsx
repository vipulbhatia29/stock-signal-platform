/**
 * Auth page render tests.
 *
 * Covers: Login page, Register page
 * Each page is tested for:
 *   - Renders without crashing
 *   - Shows expected form fields
 *   - Shows error message when auth context provides one
 */

import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AuthContext } from "@/lib/auth";

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

// Mock Next.js router
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
}));

// Mock Next.js Link component
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

// Mock lucide-react icons
jest.mock("lucide-react", () => ({
  Mail: () => <svg data-testid="mail-icon" />,
  Lock: () => <svg data-testid="lock-icon" />,
  User: () => <svg data-testid="user-icon" />,
  ArrowRight: () => <svg data-testid="arrow-icon" />,
  TrendingUp: () => <svg data-testid="trending-icon" />,
  BarChart3: () => <svg data-testid="barchart-icon" />,
  Shield: () => <svg data-testid="shield-icon" />,
}));

// Mock sonner toast
jest.mock("sonner", () => ({
  toast: { info: jest.fn(), error: jest.fn(), success: jest.fn() },
}));

// ---------------------------------------------------------------------------
// Auth context helpers
// ---------------------------------------------------------------------------

const makeAuthValue = (overrides: Partial<React.ComponentProps<typeof AuthContext.Provider>["value"]> = {}) => ({
  isAuthenticated: false,
  isLoading: false,
  error: null,
  login: jest.fn(),
  register: jest.fn(),
  logout: jest.fn(),
  clearError: jest.fn(),
  ...overrides,
});

function renderWithAuth(ui: React.ReactElement, authValue = makeAuthValue()) {
  return render(
    <AuthContext.Provider value={authValue}>{ui}</AuthContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Login page tests
// ---------------------------------------------------------------------------

describe("LoginPage", () => {
  // Lazy import so mocks are applied first
  let LoginPage: React.ComponentType;

  beforeAll(async () => {
    const mod = await import("@/app/login/page");
    LoginPage = mod.default;
  });

  it("renders without crashing", () => {
    renderWithAuth(<LoginPage />);
  });

  it("shows email input field", () => {
    renderWithAuth(<LoginPage />);
    expect(screen.getByPlaceholderText(/you@example\.com/i)).toBeInTheDocument();
  });

  it("shows password input field", () => {
    renderWithAuth(<LoginPage />);
    expect(screen.getByPlaceholderText(/••••••••/)).toBeInTheDocument();
  });

  it("shows a submit button", () => {
    renderWithAuth(<LoginPage />);
    expect(
      screen.getByRole("button", { name: /sign in/i })
    ).toBeInTheDocument();
  });

  it("shows error message when auth context has an error", () => {
    const authValue = makeAuthValue({ error: "Invalid email or password" });
    renderWithAuth(<LoginPage />, authValue);
    expect(screen.getByText(/invalid email or password/i)).toBeInTheDocument();
  });

  it("calls login with email and password on form submit", async () => {
    const login = jest.fn();
    renderWithAuth(<LoginPage />, makeAuthValue({ login }));

    fireEvent.change(screen.getByPlaceholderText(/you@example\.com/i), {
      target: { value: "test@example.com" },
    });
    fireEvent.change(screen.getByPlaceholderText(/••••••••/), {
      target: { value: "TestPass1" },
    });
    fireEvent.submit(screen.getByRole("button", { name: /sign in/i }).closest("form")!);

    await waitFor(() => {
      expect(login).toHaveBeenCalledWith("test@example.com", "TestPass1");
    });
  });

  it("disables submit button while loading", () => {
    renderWithAuth(<LoginPage />, makeAuthValue({ isLoading: true }));
    expect(screen.getByRole("button", { name: /signing in/i })).toBeDisabled();
  });

  it("shows a link to the register page", () => {
    renderWithAuth(<LoginPage />);
    expect(screen.getByRole("link", { name: /create one/i })).toHaveAttribute(
      "href",
      "/register"
    );
  });
});

// ---------------------------------------------------------------------------
// Register page tests
// ---------------------------------------------------------------------------

describe("RegisterPage", () => {
  let RegisterPage: React.ComponentType;

  beforeAll(async () => {
    const mod = await import("@/app/register/page");
    RegisterPage = mod.default;
  });

  it("renders without crashing", () => {
    renderWithAuth(<RegisterPage />);
  });

  it("shows email input field", () => {
    renderWithAuth(<RegisterPage />);
    expect(screen.getByPlaceholderText(/you@example\.com/i)).toBeInTheDocument();
  });

  it("shows password input field", () => {
    renderWithAuth(<RegisterPage />);
    expect(screen.getByPlaceholderText(/••••••••/)).toBeInTheDocument();
  });

  it("shows a submit button", () => {
    renderWithAuth(<RegisterPage />);
    expect(
      screen.getByRole("button", { name: /create account/i })
    ).toBeInTheDocument();
  });

  it("shows validation error when password is too short", async () => {
    renderWithAuth(<RegisterPage />);
    fireEvent.change(screen.getByPlaceholderText(/you@example\.com/i), {
      target: { value: "test@example.com" },
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

  it("shows error message when auth context has an error", () => {
    renderWithAuth(
      <RegisterPage />,
      makeAuthValue({ error: "Email already registered" })
    );
    expect(screen.getByText(/email already registered/i)).toBeInTheDocument();
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

  it("disables submit button while loading", () => {
    renderWithAuth(<RegisterPage />, makeAuthValue({ isLoading: true }));
    expect(
      screen.getByRole("button", { name: /creating account/i })
    ).toBeDisabled();
  });

  it("shows a link back to the login page", () => {
    renderWithAuth(<RegisterPage />);
    expect(screen.getByRole("link", { name: /sign in/i })).toHaveAttribute(
      "href",
      "/login"
    );
  });
});
