export interface ToolCall {
  id: string;
  tool: string;
  params: Record<string, unknown>;
  status: "running" | "completed" | "error";
  result?: unknown;
}

export interface EvidenceItem {
  claim: string;
  source_tool: string;
  value?: string;
  timestamp?: string;
}

export interface ChatMessageUI {
  id: string;
  role: "user" | "assistant";
  content: string;
  toolCalls: ToolCall[];
  isStreaming: boolean;
  model?: string;
  plan?: { steps: string[]; reasoning: string };
  evidence?: EvidenceItem[];
  isDecline?: boolean;
  feedback?: "positive" | "negative" | null;
}

export interface ChatState {
  messages: ChatMessageUI[];
  isStreaming: boolean;
  error: string | null;
  activeSessionId: string | null;
  agentType: "stock" | "general";
}

export type ChatAction =
  | { type: "SEND_MESSAGE"; content: string }
  | { type: "FLUSH_TOKENS"; bufferedContent: string }
  | { type: "TOOL_START"; tool: string; params: Record<string, unknown> }
  | { type: "TOOL_RESULT"; tool: string; status: string; data: unknown }
  | { type: "THINKING"; content: string }
  | { type: "STREAM_DONE"; usage: Record<string, unknown> }
  | { type: "STREAM_ERROR"; error: string }
  | { type: "PROVIDER_FALLBACK"; content: string }
  | { type: "PLAN"; steps: string[]; reasoning: string }
  | { type: "EVIDENCE"; items: EvidenceItem[] }
  | { type: "DECLINE"; content: string }
  | { type: "TOOL_ERROR"; tool: string; error: string }
  | { type: "LOAD_HISTORY"; messages: ChatMessageUI[] }
  | { type: "SET_SESSION"; sessionId: string; agentType: "stock" | "general" }
  | { type: "CLEAR_ERROR" }
  | { type: "CLEAR" };

export const initialChatState: ChatState = {
  messages: [],
  isStreaming: false,
  error: null,
  activeSessionId: null,
  agentType: "stock",
};

function genId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

function updateLastAssistant(
  messages: ChatMessageUI[],
  updater: (msg: ChatMessageUI) => ChatMessageUI
): ChatMessageUI[] {
  const updated = [...messages];
  for (let i = updated.length - 1; i >= 0; i--) {
    if (updated[i].role === "assistant") {
      updated[i] = updater({ ...updated[i] });
      break;
    }
  }
  return updated;
}

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "SEND_MESSAGE": {
      const userMsg: ChatMessageUI = {
        id: genId(),
        role: "user",
        content: action.content,
        toolCalls: [],
        isStreaming: false,
      };
      const assistantPlaceholder: ChatMessageUI = {
        id: genId(),
        role: "assistant",
        content: "",
        toolCalls: [],
        isStreaming: true,
      };
      return {
        ...state,
        messages: [...state.messages, userMsg, assistantPlaceholder],
        isStreaming: true,
        error: null,
      };
    }

    case "FLUSH_TOKENS":
      return {
        ...state,
        messages: updateLastAssistant(state.messages, (msg) => ({
          ...msg,
          content: msg.content + action.bufferedContent,
        })),
      };

    case "TOOL_START": {
      const toolCall: ToolCall = {
        id: genId(),
        tool: action.tool,
        params: action.params,
        status: "running",
      };
      return {
        ...state,
        messages: updateLastAssistant(state.messages, (msg) => ({
          ...msg,
          toolCalls: [...msg.toolCalls, toolCall],
        })),
      };
    }

    case "TOOL_RESULT":
      return {
        ...state,
        messages: updateLastAssistant(state.messages, (msg) => ({
          ...msg,
          toolCalls: msg.toolCalls.map((tc) =>
            tc.tool === action.tool && tc.status === "running"
              ? { ...tc, status: "completed" as const, result: action.data }
              : tc
          ),
        })),
      };

    case "THINKING":
      return {
        ...state,
        messages: updateLastAssistant(state.messages, (msg) => ({
          ...msg,
          content: action.content,
        })),
      };

    case "STREAM_DONE":
      return {
        ...state,
        isStreaming: false,
        messages: updateLastAssistant(state.messages, (msg) => ({
          ...msg,
          isStreaming: false,
        })),
      };

    case "STREAM_ERROR":
      return {
        ...state,
        isStreaming: false,
        error: action.error,
        messages: updateLastAssistant(state.messages, (msg) => ({
          ...msg,
          isStreaming: false,
        })),
      };

    case "PROVIDER_FALLBACK":
      return {
        ...state,
        messages: updateLastAssistant(state.messages, (msg) => ({
          ...msg,
          content: msg.content
            ? `${msg.content}\n\n_Provider fallback: ${action.content}_`
            : `_Provider fallback: ${action.content}_`,
        })),
      };

    case "PLAN":
      return {
        ...state,
        messages: updateLastAssistant(state.messages, (msg) => ({
          ...msg,
          plan: { steps: action.steps, reasoning: action.reasoning },
        })),
      };

    case "EVIDENCE":
      return {
        ...state,
        messages: updateLastAssistant(state.messages, (msg) => ({
          ...msg,
          evidence: action.items,
        })),
      };

    case "DECLINE":
      return {
        ...state,
        messages: updateLastAssistant(state.messages, (msg) => ({
          ...msg,
          content: action.content,
          isDecline: true,
        })),
      };

    case "TOOL_ERROR": {
      const errorCall: ToolCall = {
        id: genId(),
        tool: action.tool,
        params: {},
        status: "error",
        result: action.error,
      };
      return {
        ...state,
        messages: updateLastAssistant(state.messages, (msg) => ({
          ...msg,
          toolCalls: [...msg.toolCalls, errorCall],
        })),
      };
    }

    case "LOAD_HISTORY":
      return {
        ...state,
        messages: action.messages,
        isStreaming: false,
        error: null,
      };

    case "SET_SESSION":
      return {
        ...state,
        activeSessionId: action.sessionId || null,
        agentType: action.agentType,
      };

    case "CLEAR_ERROR":
      return {
        ...state,
        error: null,
      };

    case "CLEAR":
      return {
        ...initialChatState,
        activeSessionId: state.activeSessionId,
        agentType: state.agentType,
      };

    default:
      return state;
  }
}
