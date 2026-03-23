"use client";

import { BarChart3, Globe, Bot } from "lucide-react";
import { cn } from "@/lib/utils";

interface AgentSelectorProps {
  value: "stock" | "general";
  onChange: (agent: "stock" | "general") => void;
  disabled?: boolean;
}

const agents = [
  {
    id: "stock" as const,
    label: "Stock Analyst",
    description: "Signals, portfolio, SEC filings, macro",
    icon: BarChart3,
  },
  {
    id: "general" as const,
    label: "General",
    description: "News & web search only",
    icon: Globe,
  },
];

export function AgentSelector({ value, onChange, disabled }: AgentSelectorProps) {
  return (
    <div className="px-3.5 py-3 space-y-3">
      <div className="flex items-center gap-2 text-muted-foreground">
        <Bot size={16} />
        <h3 className="text-xs font-medium">Choose an Agent</h3>
      </div>
      <p className="text-[10px] text-muted-foreground">Select an agent based on what you need help with</p>
      <div className="flex gap-2">
        {agents.map((agent) => {
          const Icon = agent.icon;
          const isActive = value === agent.id;
          return (
            <button
              key={agent.id}
              onClick={() => onChange(agent.id)}
              disabled={disabled}
              className={cn(
                "flex-1 flex flex-col items-center gap-1.5 rounded-lg border px-3 py-3 text-center transition-colors",
                isActive
                  ? "border-[var(--bhi)] bg-[var(--cdim)] text-foreground"
                  : "border-border bg-card text-muted-foreground hover:border-[var(--bhi)] hover:bg-hov",
                disabled && "opacity-50 cursor-not-allowed"
              )}
            >
              <Icon size={18} className={isActive ? "text-cyan" : ""} />
              <div className="text-xs font-medium">{agent.label}</div>
              <div className="text-[9px] text-muted-foreground leading-tight">{agent.description}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
