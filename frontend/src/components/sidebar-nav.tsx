"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  Search,
  Briefcase,
  PieChart,
  Activity,
  Monitor,
  Settings,
  LogOut,
} from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useAuth } from "@/lib/auth";
import { useCurrentUser } from "@/hooks/use-current-user";
import { cn } from "@/lib/utils";
import { StaggerGroup, StaggerItem } from "@/components/motion-primitives";

interface NavItem {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  adminOnly?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/screener",  label: "Screener",  icon: Search },
  { href: "/portfolio", label: "Portfolio",  icon: Briefcase },
  { href: "/sectors",   label: "Sectors",    icon: PieChart },
  { href: "/observability", label: "Observability", icon: Activity },
  { href: "/admin/command-center", label: "Command Center", icon: Monitor, adminOnly: true },
];

export function SidebarNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { logout } = useAuth();
  const { isAdmin } = useCurrentUser();

  const visibleItems = NAV_ITEMS.filter((item) => !item.adminOnly || isAdmin);

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  return (
    <aside
      data-testid="sidebar-nav"
      className="flex flex-col items-center py-3.5 border-r border-border bg-card flex-shrink-0"
      style={{ width: "var(--sw)" }}
    >
      {/* Logo — matches login page branding */}
      <Link href="/dashboard" className="mb-5 flex-shrink-0">
        <div
          className="w-8 h-8 rounded-[8px] bg-cyan flex items-center justify-center"
          style={{ boxShadow: "0 0 18px var(--cg)" }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--background)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
            <polyline points="16 7 22 7 22 13" />
          </svg>
        </div>
      </Link>

      {/* Nav items */}
      <StaggerGroup className="flex flex-col items-center gap-1 flex-1 w-full" stagger={0.05}>
        {visibleItems.map((item) => {
          const isActive = item.href === "/dashboard"
            ? pathname === "/dashboard" || pathname === "/"
            : pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <StaggerItem key={item.href}>
            <Tooltip>
              <TooltipTrigger
                render={
                  <Link
                    href={item.href}
                    aria-label={item.label}
                    className={cn(
                      "relative w-full h-10 flex items-center justify-center",
                      isActive ? "text-cyan" : "text-subtle hover:text-muted-foreground"
                    )}
                  >
                    {/* Active left indicator */}
                    {isActive && (
                      <span
                        className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-cyan rounded-r-sm"
                        style={{ boxShadow: "0 0 8px var(--cg)" }}
                      />
                    )}
                    {/* Icon container */}
                    <span
                      className={cn(
                        "w-10 h-10 rounded-lg flex items-center justify-center transition-colors",
                        isActive ? "bg-[var(--cdim)]" : "hover:bg-hov"
                      )}
                    >
                      <Icon size={18} />
                    </span>
                  </Link>
                }
              />
              <TooltipContent side="right" className="text-xs">
                {item.label}
              </TooltipContent>
            </Tooltip>
            </StaggerItem>
          );
        })}
      </StaggerGroup>

      {/* Bottom: settings + logout — padded above Next.js dev badge */}
      <div className="flex flex-col items-center gap-1 w-full mb-8">
        {/* Account */}
        <Tooltip>
          <TooltipTrigger
            render={
              <Link
                href="/account"
                aria-label="Account"
                className={cn(
                  "relative w-full h-10 flex items-center justify-center",
                  pathname.startsWith("/account") ? "text-cyan" : "text-subtle hover:text-muted-foreground"
                )}
              >
                {pathname.startsWith("/account") && (
                  <span
                    className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-cyan rounded-r-sm"
                    style={{ boxShadow: "0 0 8px var(--cg)" }}
                  />
                )}
                <span
                  className={cn(
                    "w-10 h-10 rounded-lg flex items-center justify-center transition-colors",
                    pathname.startsWith("/account") ? "bg-[var(--cdim)]" : "hover:bg-hov"
                  )}
                >
                  <Settings size={18} />
                </span>
              </Link>
            }
          />
          <TooltipContent side="right" className="text-xs">
            Account
          </TooltipContent>
        </Tooltip>

        {/* Logout */}
        <Tooltip>
          <TooltipTrigger
            render={
              <button
                onClick={handleLogout}
                className="w-full h-10 flex items-center justify-center text-subtle hover:text-destructive transition-colors"
              >
                <span className="w-10 h-10 rounded-lg flex items-center justify-center hover:bg-destructive/10 transition-colors">
                  <LogOut size={18} />
                </span>
              </button>
            }
          />
          <TooltipContent side="right" className="text-xs">
            Logout
          </TooltipContent>
        </Tooltip>
      </div>
    </aside>
  );
}
