"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  Search,
  Briefcase,
  PieChart,
  Settings,
  LogOut,
} from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { StaggerGroup, StaggerItem } from "@/components/motion-primitives";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/screener",  label: "Screener",  icon: Search },
  { href: "/portfolio", label: "Portfolio",  icon: Briefcase },
  { href: "/sectors",   label: "Sectors",    icon: PieChart },
] as const;

export function SidebarNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { logout } = useAuth();

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  return (
    <aside
      className="flex flex-col items-center py-3.5 border-r border-border bg-card flex-shrink-0"
      style={{ width: "var(--sw)" }}
    >
      {/* Logo */}
      <div
        className="w-8 h-8 rounded-[8px] bg-cyan flex items-center justify-center mb-5 flex-shrink-0"
        style={{ boxShadow: "0 0 18px var(--cg)" }}
      >
        <span className="text-[var(--background)] font-bold text-sm leading-none flex items-center justify-center w-full h-full">
          S
        </span>
      </div>

      {/* Nav items */}
      <StaggerGroup className="flex flex-col items-center gap-1 flex-1 w-full" stagger={0.05}>
        {NAV_ITEMS.map((item) => {
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

      {/* Bottom: settings + logout */}
      <div className="flex flex-col items-center gap-1 w-full">
        {/* Settings — disabled */}
        <Tooltip>
          <TooltipTrigger
            render={
              <button className="w-full h-10 flex items-center justify-center text-subtle/40 cursor-not-allowed">
                <span className="w-10 h-10 rounded-lg flex items-center justify-center">
                  <Settings size={18} />
                </span>
              </button>
            }
          />
          <TooltipContent side="right" className="text-xs">
            Settings (Coming Soon)
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
