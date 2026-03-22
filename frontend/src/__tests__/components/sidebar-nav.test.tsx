import React from "react";
import { render, screen } from "@testing-library/react";
import { SidebarNav } from "@/components/sidebar-nav";

// Mock next/navigation
jest.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => ({ push: jest.fn() }),
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

// Mock shadcn UI Tooltip components
jest.mock("@/components/ui/tooltip", () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ render }: { render: React.ReactElement }) => <>{render}</>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <span data-testid="tooltip">{children}</span>,
}));

// Mock lucide-react icons
jest.mock("lucide-react", () => ({
  LayoutDashboard: () => <svg data-testid="icon-dashboard" />,
  Search: () => <svg data-testid="icon-screener" />,
  Briefcase: () => <svg data-testid="icon-portfolio" />,
  PieChart: () => <svg data-testid="icon-sectors" />,
  Settings: () => <svg data-testid="icon-settings" />,
  LogOut: () => <svg data-testid="icon-logout" />,
}));

test("renders all navigation links including Sectors", () => {
  render(<SidebarNav />);
  expect(screen.getByLabelText("Dashboard")).toBeInTheDocument();
  expect(screen.getByLabelText("Screener")).toBeInTheDocument();
  expect(screen.getByLabelText("Portfolio")).toBeInTheDocument();
  expect(screen.getByLabelText("Sectors")).toBeInTheDocument();
});

test("Dashboard link has active styling when on /dashboard", () => {
  render(<SidebarNav />);
  const dashboardLink = screen.getByLabelText("Dashboard");
  expect(dashboardLink.className).toContain("text-cyan");
});

test("non-active link does not have active styling", () => {
  render(<SidebarNav />);
  const screenerLink = screen.getByLabelText("Screener");
  expect(screenerLink.className).not.toContain("text-cyan");
});

test("renders logout button", () => {
  render(<SidebarNav />);
  expect(screen.getByTestId("icon-logout")).toBeInTheDocument();
});
