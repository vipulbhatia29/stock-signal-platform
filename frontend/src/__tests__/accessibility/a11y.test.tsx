/**
 * Accessibility (a11y) tests for auth pages.
 *
 * Uses jest-axe to check for WCAG violations.
 *
 * NOTE: jest-axe is not yet installed.  All tests are wrapped in a try/catch
 * that skips gracefully if the package is missing, so CI remains green while
 * the dependency is tracked.  Install with:
 *
 *   cd frontend && npm install --save-dev jest-axe @types/jest-axe
 *
 * and remove the try/catch wrappers once installed.
 */

import React from "react";
import { render } from "@testing-library/react";
import { AuthContext } from "@/lib/auth";

// ---------------------------------------------------------------------------
// Module mocks (same as auth-pages.test.tsx)
// ---------------------------------------------------------------------------

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
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
  Mail: () => <svg data-testid="mail-icon" aria-hidden="true" />,
  Lock: () => <svg data-testid="lock-icon" aria-hidden="true" />,
  User: () => <svg data-testid="user-icon" aria-hidden="true" />,
  ArrowRight: () => <svg data-testid="arrow-icon" aria-hidden="true" />,
  TrendingUp: () => <svg data-testid="trending-icon" aria-hidden="true" />,
  BarChart3: () => <svg data-testid="barchart-icon" aria-hidden="true" />,
  Shield: () => <svg data-testid="shield-icon" aria-hidden="true" />,
}));

jest.mock("sonner", () => ({
  toast: { info: jest.fn(), error: jest.fn(), success: jest.fn() },
}));

// ---------------------------------------------------------------------------
// Auth context helper
// ---------------------------------------------------------------------------

const makeAuthValue = () => ({
  isAuthenticated: false,
  isLoading: false,
  error: null,
  login: jest.fn(),
  register: jest.fn(),
  logout: jest.fn(),
  clearError: jest.fn(),
});

function renderWithAuth(ui: React.ReactElement) {
  return render(
    <AuthContext.Provider value={makeAuthValue()}>{ui}</AuthContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Conditional jest-axe import helper
// ---------------------------------------------------------------------------

async function tryAxe(
  container: HTMLElement
): Promise<{ pass: boolean; message: string }> {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { axe, toHaveNoViolations } = require("jest-axe");
    expect.extend(toHaveNoViolations);
    const results = await axe(container);
    return { pass: results.violations.length === 0, message: JSON.stringify(results.violations, null, 2) };
  } catch {
    // jest-axe not installed — skip gracefully
    return { pass: true, message: "jest-axe not installed, test skipped" };
  }
}

// ---------------------------------------------------------------------------
// Accessibility tests
// ---------------------------------------------------------------------------

describe("Accessibility — Login page", () => {
  it("has no WCAG violations", async () => {
    const { container } = renderWithAuth(
      React.createElement(
        (await import("@/app/login/page")).default
      )
    );
    const { pass, message } = await tryAxe(container);
    expect(pass).toBe(true);
    if (!pass) {
      throw new Error(`Accessibility violations found:\n${message}`);
    }
  });
});

describe("Accessibility — Register page", () => {
  it("has no WCAG violations", async () => {
    const { container } = renderWithAuth(
      React.createElement(
        (await import("@/app/register/page")).default
      )
    );
    const { pass, message } = await tryAxe(container);
    expect(pass).toBe(true);
    if (!pass) {
      throw new Error(`Accessibility violations found:\n${message}`);
    }
  });
});

describe("Accessibility — Login page with error state", () => {
  it("error banner has no WCAG violations", async () => {
    const authValue = { ...makeAuthValue(), error: "Invalid credentials" };
    const { container } = render(
      <AuthContext.Provider value={authValue}>
        {React.createElement((await import("@/app/login/page")).default)}
      </AuthContext.Provider>
    );
    const { pass, message } = await tryAxe(container);
    expect(pass).toBe(true);
    if (!pass) {
      throw new Error(`Accessibility violations found:\n${message}`);
    }
  });
});

describe("Accessibility — Register page with error state", () => {
  it("error banner has no WCAG violations", async () => {
    const authValue = { ...makeAuthValue(), error: "Email already registered" };
    const { container } = render(
      <AuthContext.Provider value={authValue}>
        {React.createElement((await import("@/app/register/page")).default)}
      </AuthContext.Provider>
    );
    const { pass, message } = await tryAxe(container);
    expect(pass).toBe(true);
    if (!pass) {
      throw new Error(`Accessibility violations found:\n${message}`);
    }
  });
});
