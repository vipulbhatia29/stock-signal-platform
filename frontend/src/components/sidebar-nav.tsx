"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  SlidersHorizontal,
  PieChart,
  Settings,
} from "lucide-react";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/screener",  label: "Screener",  icon: SlidersHorizontal },
  { href: "/portfolio", label: "Portfolio",  icon: PieChart },
] as const;

export function SidebarNav() {
  const pathname = usePathname();
  const { logout } = useAuth();

  return (
    <aside
      className="flex flex-col items-center py-3.5 border-r border-border bg-card flex-shrink-0"
      style={{ width: "var(--sw)" }}
    >
      {/* Logo */}
      <div
        className="w-7 h-7 rounded-[7px] bg-cyan flex items-center justify-center mb-5 flex-shrink-0"
        style={{ boxShadow: "0 0 18px var(--cg)" }}
      >
        <span className="text-[var(--background)] font-bold text-sm leading-none flex items-center justify-center w-full h-full">
          S
        </span>
      </div>

      {/* Nav items */}
      <nav className="flex flex-col items-center gap-0.5 flex-1 w-full">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-label={item.label}
              className={cn(
                "relative w-full h-10 flex items-center justify-center group",
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
                  "w-8 h-8 rounded-[7px] flex items-center justify-center transition-colors",
                  isActive ? "bg-[var(--cdim)]" : "group-hover:bg-hov"
                )}
              >
                <Icon size={16} />
              </span>
              {/* CSS tooltip */}
              <span
                className="absolute left-[calc(100%+8px)] top-1/2 -translate-y-1/2 bg-card2 border border-border text-foreground text-[11px] px-2 py-0.5 rounded-[5px] whitespace-nowrap pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity z-50"
              >
                {item.label}
              </span>
            </Link>
          );
        })}
      </nav>

      {/* Bottom: settings placeholder + user avatar with logout */}
      <div className="flex flex-col items-center gap-0.5 w-full">
        {/* Settings — placeholder, no page yet */}
        <div className="relative w-full h-10 flex items-center justify-center group text-subtle">
          <span className="w-8 h-8 rounded-[7px] flex items-center justify-center group-hover:bg-hov transition-colors">
            <Settings size={16} />
          </span>
          <span className="absolute left-[calc(100%+8px)] top-1/2 -translate-y-1/2 bg-card2 border border-border text-foreground text-[11px] px-2 py-0.5 rounded-[5px] whitespace-nowrap pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity z-50">
            Settings (coming soon)
          </span>
        </div>

        {/* User avatar with logout popover */}
        <Popover>
          <PopoverTrigger asChild>
            <button
              className="w-[26px] h-[26px] rounded-full flex items-center justify-center text-[10px] font-bold text-white cursor-pointer mt-1"
              style={{ background: "linear-gradient(135deg, #38bdf8, #6366f1)" }}
              aria-label="User menu"
            >
              U
            </button>
          </PopoverTrigger>
          <PopoverContent
            side="right"
            align="end"
            className="w-32 p-1 bg-card2 border-border"
          >
            <Button
              variant="ghost"
              size="sm"
              className="w-full justify-start text-muted-foreground hover:text-foreground text-xs"
              onClick={logout}
            >
              Logout
            </Button>
          </PopoverContent>
        </Popover>
      </div>
    </aside>
  );
}
