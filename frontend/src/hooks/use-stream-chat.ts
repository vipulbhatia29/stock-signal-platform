import { useReducer, useRef, useCallback, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { chatReducer, initialChatState } from "./chat-reducer";
import { parseNDJSONLines } from "@/lib/ndjson-parser";
import { STORAGE_KEYS } from "@/lib/storage-keys";

const API_BASE = "/api/v1";

export function useStreamChat() {
  const [state, dispatch] = useReducer(chatReducer, initialChatState);
  const queryClient = useQueryClient();
  const abortRef = useRef<AbortController | null>(null);
  const tokenBufferRef = useRef("");
  const rafRef = useRef<number>(0);
  const mountedRef = useRef(true);
  const lastUserMessageRef = useRef<string>("");
  const activeSessionIdRef = useRef<string | null>(state.activeSessionId);

  // Restore active session from localStorage on mount + cleanup on unmount
  useEffect(() => {
    mountedRef.current = true;
    const savedSessionId = localStorage.getItem(STORAGE_KEYS.CHAT_ACTIVE_SESSION);
    if (savedSessionId) {
      dispatch({ type: "SET_SESSION", sessionId: savedSessionId, agentType: "stock" });
    }
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  // Keep ref in sync with state to avoid stale closure in sendMessage
  useEffect(() => {
    activeSessionIdRef.current = state.activeSessionId;
  }, [state.activeSessionId]);

  // Token batching: accumulate in ref, flush via RAF
  const scheduleFlush = useCallback(() => {
    if (rafRef.current) return;
    rafRef.current = requestAnimationFrame(() => {
      if (mountedRef.current && tokenBufferRef.current) {
        dispatch({
          type: "FLUSH_TOKENS",
          bufferedContent: tokenBufferRef.current,
        });
        tokenBufferRef.current = "";
      }
      rafRef.current = 0;
    });
  }, []);

  const sendMessage = useCallback(
    async (content: string) => {
      if (state.isStreaming) return;
      lastUserMessageRef.current = content;
      dispatch({ type: "SEND_MESSAGE", content });

      abortRef.current = new AbortController();
      const body = {
        message: content,
        session_id: state.activeSessionId ?? undefined,
        agent_type: state.activeSessionId ? undefined : state.agentType,
      };

      let response: Response;
      try {
        response = await fetch(`${API_BASE}/chat/stream`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
          signal: abortRef.current.signal,
        });
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        dispatch({
          type: "STREAM_ERROR",
          error: "Network error — check your connection",
        });
        return;
      }

      // Auth retry on 401
      if (response.status === 401) {
        try {
          const refreshRes = await fetch(`${API_BASE}/auth/refresh`, {
            method: "POST",
            credentials: "include",
          });
          if (refreshRes.ok) {
            response = await fetch(`${API_BASE}/chat/stream`, {
              method: "POST",
              credentials: "include",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(body),
              signal: abortRef.current.signal,
            });
          }
        } catch {
          /* fall through to error handling */
        }
      }

      if (!response.ok) {
        if (response.status === 401) {
          window.location.href = "/login";
          return;
        }
        let detail = `Server error (${response.status})`;
        try {
          const errBody = await response.json();
          detail = errBody.detail || detail;
        } catch {
          /* non-JSON error body */
        }
        dispatch({ type: "STREAM_ERROR", error: detail });
        return;
      }

      // Stream NDJSON
      const reader = response.body?.getReader();
      if (!reader) {
        dispatch({ type: "STREAM_ERROR", error: "No response body" });
        return;
      }

      const decoder = new TextDecoder("utf-8", { fatal: false });
      let buffer = "";

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          if (!mountedRef.current) break;

          const chunk = decoder.decode(value, { stream: true });
          const { events, remainder } = parseNDJSONLines(chunk, buffer);
          buffer = remainder;

          for (const event of events) {
            switch (event.type) {
              case "token":
                tokenBufferRef.current += event.content ?? "";
                scheduleFlush();
                break;
              case "thinking":
                dispatch({
                  type: "THINKING",
                  content: event.content ?? "",
                });
                break;
              case "tool_start":
                dispatch({
                  type: "TOOL_START",
                  tool: event.tool ?? "",
                  params: (event.params as Record<string, unknown>) ?? {},
                });
                break;
              case "tool_result":
                dispatch({
                  type: "TOOL_RESULT",
                  tool: event.tool ?? "",
                  status: event.status ?? "ok",
                  data: event.data,
                });
                break;
              case "done":
                // Flush any remaining tokens
                if (tokenBufferRef.current) {
                  dispatch({
                    type: "FLUSH_TOKENS",
                    bufferedContent: tokenBufferRef.current,
                  });
                  tokenBufferRef.current = "";
                }
                dispatch({
                  type: "STREAM_DONE",
                  usage: (event.usage as Record<string, unknown>) ?? {},
                });
                // Invalidate session list + messages cache
                queryClient.invalidateQueries({
                  queryKey: ["chat", "sessions"],
                });
                if (activeSessionIdRef.current) {
                  queryClient.invalidateQueries({
                    queryKey: ["chat", "messages", activeSessionIdRef.current],
                  });
                }
                break;
              case "error":
                dispatch({
                  type: "STREAM_ERROR",
                  error: event.error ?? "Unknown error",
                });
                break;
              case "provider_fallback":
                dispatch({
                  type: "PROVIDER_FALLBACK",
                  content: event.content ?? "",
                });
                break;
              case "context_truncated":
                // Informational — no user action needed
                break;
              case "plan":
                dispatch({
                  type: "PLAN",
                  steps: ((event.data as Record<string, unknown>)?.steps as string[]) ?? [],
                  reasoning: event.content ?? "",
                });
                break;
              case "evidence":
                dispatch({
                  type: "EVIDENCE",
                  items: (event.data as Array<{
                    claim: string;
                    source_tool: string;
                    value?: string;
                    timestamp?: string;
                  }>) ?? [],
                });
                break;
              case "decline":
                dispatch({
                  type: "DECLINE",
                  content: event.content ?? "I can only help with financial analysis.",
                });
                break;
              case "tool_error":
                dispatch({
                  type: "TOOL_ERROR",
                  tool: event.tool ?? "unknown",
                  error: event.error ?? "Tool failed",
                });
                break;
            }
          }
        }
      } catch (err) {
        if ((err as Error).name !== "AbortError" && mountedRef.current) {
          // Flush partial tokens before showing error
          if (tokenBufferRef.current) {
            dispatch({
              type: "FLUSH_TOKENS",
              bufferedContent: tokenBufferRef.current,
            });
            tokenBufferRef.current = "";
          }
          dispatch({ type: "STREAM_ERROR", error: "Stream interrupted" });
        }
      }
    },
    [
      state.isStreaming,
      state.activeSessionId,
      state.agentType,
      scheduleFlush,
      queryClient,
    ]
  );

  const stopGeneration = useCallback(() => {
    abortRef.current?.abort();
    if (tokenBufferRef.current) {
      dispatch({
        type: "FLUSH_TOKENS",
        bufferedContent: tokenBufferRef.current,
      });
      tokenBufferRef.current = "";
    }
    dispatch({ type: "STREAM_DONE", usage: {} });
  }, []);

  const retry = useCallback(() => {
    if (lastUserMessageRef.current) {
      dispatch({ type: "CLEAR" });
      sendMessage(lastUserMessageRef.current);
    }
  }, [sendMessage]);

  const switchSession = useCallback((sessionId: string) => {
    abortRef.current?.abort();
    dispatch({ type: "SET_SESSION", sessionId, agentType: "stock" });
    localStorage.setItem(STORAGE_KEYS.CHAT_ACTIVE_SESSION, sessionId);
  }, []);

  const startNewSession = useCallback(
    (agentType: "stock" | "general") => {
      abortRef.current?.abort();
      dispatch({ type: "CLEAR" });
      dispatch({ type: "SET_SESSION", sessionId: "", agentType });
      localStorage.removeItem(STORAGE_KEYS.CHAT_ACTIVE_SESSION);
    },
    []
  );

  const clearError = useCallback(() => {
    dispatch({ type: "CLEAR_ERROR" });
  }, []);

  const setAgentType = useCallback((agentType: "stock" | "general") => {
    dispatch({ type: "SET_SESSION", sessionId: "", agentType });
  }, []);

  return {
    messages: state.messages,
    isStreaming: state.isStreaming,
    error: state.error,
    activeSessionId: state.activeSessionId,
    agentType: state.agentType,
    sendMessage,
    stopGeneration,
    retry,
    switchSession,
    startNewSession,
    clearError,
    setAgentType,
  };
}
