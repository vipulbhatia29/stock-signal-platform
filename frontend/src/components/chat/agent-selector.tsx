"use client";

interface AgentSelectorProps {
  value: "stock" | "general";
  onChange: (agent: "stock" | "general") => void;
  disabled?: boolean;
}

const agents = [
  {
    id: "stock" as const,
    label: "Stock Analyst",
    description: "Full toolkit access",
  },
  {
    id: "general" as const,
    label: "General Assistant",
    description: "News & web search",
  },
];

export function AgentSelector({ value, onChange, disabled }: AgentSelectorProps) {
  return (
    <div className="flex gap-2 px-3 py-2">
      {agents.map((agent) => (
        <button
          key={agent.id}
          onClick={() => onChange(agent.id)}
          disabled={disabled}
          className={`flex-1 rounded-md border px-3 py-2 text-left text-xs transition-colors ${
            value === agent.id
              ? "border-accent bg-accent/10 text-foreground"
              : "border-border bg-card text-muted-foreground hover:border-accent/50"
          } ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
        >
          <div className="font-medium">{agent.label}</div>
          <div className="text-[10px] text-muted-foreground">{agent.description}</div>
        </button>
      ))}
    </div>
  );
}
