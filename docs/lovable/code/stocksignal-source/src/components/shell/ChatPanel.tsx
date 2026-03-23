import { useState, useRef, useEffect } from "react";
import { Bot, X, Send, Square, MessageSquare, ChevronDown, Check, Loader2, AlertCircle, Copy, Download, Trash2, Plus, Sparkles, BarChart3, Globe } from "lucide-react";
import { cn } from "@/lib/utils";
import { MOCK_CHAT_MESSAGES, MOCK_CHAT_SESSIONS, type ChatMessage, type ToolCall, type ChatSession } from "@/lib/mock-data";

interface ChatPanelProps {
  open: boolean;
  onClose: () => void;
}

export function ChatPanel({ open, onClose }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [agentType, setAgentType] = useState<"stock" | "general" | null>(null);
  const [showSessions, setShowSessions] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = () => {
    if (!input.trim()) return;
    if (!agentType) setAgentType("stock");
    const userMsg: ChatMessage = { id: `u-${Date.now()}`, role: "user", content: input, timestamp: new Date() };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setStreaming(true);
    // Simulate streaming response
    setTimeout(() => {
      setMessages((prev) => [...prev, ...MOCK_CHAT_MESSAGES.filter((m) => m.role === "assistant")]);
      setStreaming(false);
    }, 1500);
  };

  const loadDemo = () => {
    setAgentType("stock");
    setMessages(MOCK_CHAT_MESSAGES);
  };

  return (
    <div className={cn(
      "flex h-screen flex-col border-l border-border bg-card transition-all duration-300 ease-in-out",
      open ? "w-[360px] opacity-100" : "w-0 opacity-0 overflow-hidden border-l-0"
    )}>
      {/* Header */}
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-border px-3">
        <div className="flex items-center gap-2">
          <div className="relative">
            <Bot className="h-4 w-4 text-primary" />
            <span className="absolute -bottom-0.5 -right-0.5 h-1.5 w-1.5 rounded-full bg-gain border border-card" />
          </div>
          <div>
            <span className="text-sm font-medium">AI Analyst</span>
            <p className="text-[9px] text-muted-foreground -mt-0.5">Powered by Claude</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setShowSessions(!showSessions)}
            className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-hov hover:text-foreground transition-colors"
          >
            <MessageSquare className="h-3.5 w-3.5" />
          </button>
          <button onClick={onClose} className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-hov hover:text-foreground transition-colors">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Session list */}
      {showSessions && (
        <div className="border-b border-border p-3 space-y-2">
          <button className="w-full flex items-center justify-center gap-1.5 rounded-lg border border-dashed border-border py-2 text-xs text-muted-foreground hover:text-foreground hover:border-primary/30 transition-colors">
            <Plus className="h-3 w-3" />
            New Chat
          </button>
          {MOCK_CHAT_SESSIONS.map((s) => (
            <SessionRow key={s.id} session={s} active={false} onClick={() => { loadDemo(); setShowSessions(false); }} />
          ))}
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {!agentType && messages.length === 0 ? (
          <AgentSelector onSelect={(type) => { setAgentType(type); }} />
        ) : messages.length === 0 ? (
          <SuggestionChips onSelect={(msg) => { setInput(msg); }} />
        ) : (
          <div className="p-3 space-y-4">
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            {streaming && <ThinkingIndicator />}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-border p-3">
        <div className="flex items-end gap-2 rounded-lg bg-card2 border border-border px-3 py-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
            placeholder="Ask about stocks, portfolio, signals..."
            rows={1}
            className="flex-1 resize-none bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none max-h-24"
          />
          <button
            onClick={streaming ? () => setStreaming(false) : handleSend}
            className={cn(
              "flex h-7 w-7 shrink-0 items-center justify-center rounded-md transition-colors",
              streaming
                ? "bg-loss/15 text-loss hover:bg-loss/25"
                : "bg-primary text-primary-foreground hover:bg-primary/90"
            )}
          >
            {streaming ? <Square className="h-3 w-3" /> : <Send className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>
    </div>
  );
}

// ======================== Sub-components ========================

function AgentSelector({ onSelect }: { onSelect: (type: "stock" | "general") => void }) {
  return (
    <div className="flex flex-col items-center justify-center h-full p-6">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10">
        <Bot className="h-6 w-6 text-primary" />
      </div>
      <h3 className="text-sm font-semibold mb-1">Choose an Agent</h3>
      <p className="text-[10px] text-muted-foreground mb-5 text-center">Select an agent based on what you need help with</p>
      <div className="grid grid-cols-2 gap-3 w-full">
        <button
          onClick={() => onSelect("stock")}
          className="flex flex-col items-center gap-2 rounded-lg border-2 border-primary/30 bg-primary/5 p-4 text-left hover:bg-primary/10 transition-colors"
        >
          <BarChart3 className="h-5 w-5 text-primary" />
          <span className="text-xs font-semibold">Stock Analyst</span>
          <span className="text-[9px] text-muted-foreground text-center leading-tight">Signals, portfolio, SEC filings, macro</span>
        </button>
        <button
          onClick={() => onSelect("general")}
          className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card2 p-4 text-left hover:bg-hov transition-colors"
        >
          <Globe className="h-5 w-5 text-muted-foreground" />
          <span className="text-xs font-semibold">General</span>
          <span className="text-[9px] text-muted-foreground text-center leading-tight">News & web search only</span>
        </button>
      </div>
    </div>
  );
}

function SuggestionChips({ onSelect }: { onSelect: (msg: string) => void }) {
  const suggestions = [
    "Analyze my portfolio",
    "Best signals today",
    "What's happening with NVDA?",
    "Top sector momentum",
  ];
  return (
    <div className="flex flex-col items-center justify-center h-full p-6">
      <Sparkles className="h-5 w-5 text-primary mb-3" />
      <p className="text-sm font-medium mb-1">Stock Signal AI</p>
      <p className="text-[10px] text-muted-foreground mb-5">Try one of these to get started</p>
      <div className="flex flex-col gap-2 w-full">
        {suggestions.map((s) => (
          <button
            key={s}
            onClick={() => onSelect(s)}
            className="text-left rounded-lg border border-border bg-card2 px-3 py-2.5 text-xs text-muted-foreground hover:text-foreground hover:border-primary/30 hover:bg-hov transition-colors"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-xl rounded-br-md bg-primary/15 px-3.5 py-2.5 text-sm text-foreground">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {message.toolCalls?.map((tc) => <ToolCard key={tc.id} tool={tc} />)}
      <div className="text-sm text-foreground leading-relaxed prose prose-invert prose-sm max-w-none prose-p:my-1.5 prose-headings:text-foreground prose-strong:text-foreground prose-th:text-muted-foreground prose-td:text-foreground prose-td:font-mono prose-td:text-xs">
        <MarkdownContent content={message.content} />
      </div>
    </div>
  );
}

function MarkdownContent({ content }: { content: string }) {
  // Simple markdown rendering — tables, bold, lists, headings
  const lines = content.split("\n");
  const elements: React.ReactNode[] = [];
  let i = 0;
  let tableRows: string[][] = [];
  let inTable = false;

  while (i < lines.length) {
    const line = lines[i];

    // Table detection
    if (line.includes("|") && line.trim().startsWith("|")) {
      if (!inTable) {
        inTable = true;
        tableRows = [];
      }
      if (!line.match(/^\|[\s-|]+\|$/)) {
        const cells = line.split("|").filter(Boolean).map((c) => c.trim());
        tableRows.push(cells);
      }
      i++;
      continue;
    }

    if (inTable) {
      inTable = false;
      elements.push(
        <div key={`table-${i}`} className="overflow-x-auto my-2">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border">
                {tableRows[0]?.map((h, j) => (
                  <th key={j} className="px-2 py-1.5 text-left text-muted-foreground font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tableRows.slice(1).map((row, ri) => (
                <tr key={ri} className="border-b border-border/50">
                  {row.map((cell, ci) => (
                    <td key={ci} className="px-2 py-1.5">{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      continue;
    }

    if (line.startsWith("### ")) {
      elements.push(<h4 key={i} className="text-xs font-semibold mt-3 mb-1">{line.slice(4)}</h4>);
    } else if (line.startsWith("## ")) {
      elements.push(<h3 key={i} className="text-sm font-semibold mt-3 mb-1">{line.slice(3)}</h3>);
    } else if (line.match(/^\d+\.\s/)) {
      const text = line.replace(/^\d+\.\s/, "");
      elements.push(<p key={i} className="ml-4 text-sm">{renderInline(text)}</p>);
    } else if (line.startsWith("- ")) {
      elements.push(<p key={i} className="ml-3 text-sm">• {renderInline(line.slice(2))}</p>);
    } else if (line.trim() === "") {
      elements.push(<div key={i} className="h-1" />);
    } else {
      elements.push(<p key={i} className="text-sm">{renderInline(line)}</p>);
    }
    i++;
  }

  // Flush remaining table
  if (inTable && tableRows.length > 0) {
    elements.push(
      <div key="table-end" className="overflow-x-auto my-2">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border">
              {tableRows[0]?.map((h, j) => (
                <th key={j} className="px-2 py-1.5 text-left text-muted-foreground font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tableRows.slice(1).map((row, ri) => (
              <tr key={ri} className="border-b border-border/50">
                {row.map((cell, ci) => (
                  <td key={ci} className="px-2 py-1.5">{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return <>{elements}</>;
}

function renderInline(text: string): React.ReactNode {
  // Simple bold handling
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i} className="font-semibold">{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

function ToolCard({ tool }: { tool: ToolCall }) {
  const [expanded, setExpanded] = useState(false);
  const icon = tool.status === "running" ? <Loader2 className="h-3 w-3 animate-spin text-primary" /> :
    tool.status === "completed" ? <Check className="h-3 w-3 text-gain" /> :
    <AlertCircle className="h-3 w-3 text-loss" />;

  return (
    <div className="rounded-lg border border-border bg-card2 overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-hov transition-colors"
      >
        {icon}
        <span className="text-xs font-mono text-muted-foreground">{tool.name}</span>
        {tool.result && <span className="ml-auto text-[10px] text-muted-foreground truncate max-w-[150px]">{tool.result}</span>}
        <ChevronDown className={cn("h-3 w-3 text-muted-foreground transition-transform shrink-0", expanded && "rotate-180")} />
      </button>
      {expanded && tool.result && (
        <div className="border-t border-border px-3 py-2 text-xs font-mono text-muted-foreground">
          {tool.result}
          <div className="flex gap-2 mt-2">
            <button className="flex items-center gap-1 text-[9px] text-muted-foreground hover:text-foreground">
              <Copy className="h-2.5 w-2.5" /> Copy
            </button>
            <button className="flex items-center gap-1 text-[9px] text-muted-foreground hover:text-foreground">
              <Download className="h-2.5 w-2.5" /> CSV
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-2 px-1">
      <div className="flex gap-1">
        {[0, 1, 2].map((i) => (
          <span key={i} className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse-subtle" style={{ animationDelay: `${i * 0.3}s` }} />
        ))}
      </div>
      <span className="text-xs text-muted-foreground">Analyzing your question...</span>
    </div>
  );
}

function SessionRow({ session, active, onClick }: { session: ChatSession; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "group flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left transition-colors",
        active ? "bg-primary/10 border border-primary/20" : "hover:bg-hov"
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-medium truncate">{session.title}</span>
          <span className={cn(
            "rounded px-1 py-0.5 text-[8px] font-medium",
            session.agentType === "stock" ? "bg-primary/15 text-primary" : "bg-muted text-muted-foreground"
          )}>
            {session.agentType === "stock" ? "Stock" : "General"}
          </span>
          {session.expired && <span className="text-[8px] text-muted-foreground">expired</span>}
        </div>
        <p className="text-[10px] text-muted-foreground truncate">{session.lastMessage}</p>
      </div>
      <button className="hidden group-hover:flex h-5 w-5 items-center justify-center rounded text-muted-foreground hover:text-loss">
        <Trash2 className="h-3 w-3" />
      </button>
    </button>
  );
}
