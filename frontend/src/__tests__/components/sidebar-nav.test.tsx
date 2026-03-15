import React from "react";
import { render, screen } from "@testing-library/react";
import { SidebarNav } from "@/components/sidebar-nav";

// Mock next/navigation
jest.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
}));

// Mock next/link
jest.mock("next/link", () => {
  const Link = ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => (
    <a href={href} {...props}>
      {children}
    </a>
  );
  Link.displayName = "Link";
  return Link;
});

// Mock useAuth
jest.mock("@/lib/auth", () => ({
  useAuth: () => ({ logout: jest.fn() }),
}));

// Mock shadcn UI Popover components
jest.mock("@/components/ui/popover", () => ({
  Popover: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  PopoverTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  PopoverContent: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

// Mock shadcn Button
jest.mock("@/components/ui/button", () => ({
  Button: ({ children, onClick, ...props }: { children: React.ReactNode; onClick?: () => void; [key: string]: unknown }) => (
    <button onClick={onClick} {...props}>
      {children}
    </button>
  ),
}));

// Mock lucide-react icons
jest.mock("lucide-react", () => ({
  LayoutDashboard: () => <svg data-testid="icon-dashboard" />,
  SlidersHorizontal: () => <svg data-testid="icon-screener" />,
  PieChart: () => <svg data-testid="icon-portfolio" />,
  Settings: () => <svg data-testid="icon-settings" />,
}));

test("renders navigation links", () => {
  render(<SidebarNav />);
  expect(screen.getByLabelText("Dashboard")).toBeInTheDocument();
  expect(screen.getByLabelText("Screener")).toBeInTheDocument();
  expect(screen.getByLabelText("Portfolio")).toBeInTheDocument();
});

test("Dashboard link has active styling when on /dashboard", () => {
  render(<SidebarNav />);
  const dashboardLink = screen.getByLabelText("Dashboard");
  // Active link has text-cyan class applied
  expect(dashboardLink.className).toContain("text-cyan");
});

test("non-active link does not have active styling", () => {
  render(<SidebarNav />);
  const screenerLink = screen.getByLabelText("Screener");
  expect(screenerLink.className).not.toContain("text-cyan");
});
