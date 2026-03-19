import { LayoutDashboard, Search, Briefcase, Settings, LogOut, PieChart } from "lucide-react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import logo from "@/assets/logo.png";

const NAV_ITEMS = [
  { icon: LayoutDashboard, label: "Dashboard", to: "/" },
  { icon: Search, label: "Screener", to: "/screener" },
  { icon: Briefcase, label: "Portfolio", to: "/portfolio" },
  { icon: PieChart, label: "Sectors", to: "/sectors" },
];

export function SidebarNav() {
  const { pathname } = useLocation();
  const navigate = useNavigate();

  return (
    <nav className="flex h-screen w-[54px] flex-col items-center border-r border-sidebar-border bg-sidebar py-4">
      <div className="mb-6 flex h-8 w-8 items-center justify-center">
        <img src={logo} alt="Stock Signal" className="h-8 w-8 drop-shadow-[0_0_8px_hsl(var(--primary)/0.4)]" />
      </div>

      <div className="flex flex-1 flex-col items-center gap-1">
        {NAV_ITEMS.map(({ icon: Icon, label, to }) => {
          const active = to === "/" ? pathname === "/" : pathname.startsWith(to);
          return (
            <Tooltip key={to} delayDuration={0}>
              <TooltipTrigger asChild>
                <NavLink
                  to={to}
                  className={cn(
                    "relative flex h-10 w-10 items-center justify-center rounded-lg transition-colors",
                    active ? "bg-sidebar-accent text-primary" : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                  )}
                >
                  {active && <span className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r bg-primary" />}
                  <Icon className="h-[18px] w-[18px]" />
                </NavLink>
              </TooltipTrigger>
              <TooltipContent side="right" className="text-xs">{label}</TooltipContent>
            </Tooltip>
          );
        })}
      </div>

      <div className="flex flex-col items-center gap-1">
        <Tooltip delayDuration={0}>
          <TooltipTrigger asChild>
            <button className="flex h-10 w-10 items-center justify-center rounded-lg text-sidebar-foreground/40 cursor-not-allowed">
              <Settings className="h-[18px] w-[18px]" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="right" className="text-xs">Settings (Coming Soon)</TooltipContent>
        </Tooltip>
        <Tooltip delayDuration={0}>
          <TooltipTrigger asChild>
            <button
              onClick={() => navigate("/login")}
              className="flex h-10 w-10 items-center justify-center rounded-lg text-sidebar-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
            >
              <LogOut className="h-[18px] w-[18px]" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="right" className="text-xs">Logout</TooltipContent>
        </Tooltip>
      </div>
    </nav>
  );
}
