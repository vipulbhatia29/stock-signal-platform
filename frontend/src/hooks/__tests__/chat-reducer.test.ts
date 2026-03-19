import { chatReducer, initialChatState } from "../chat-reducer";

describe("chatReducer", () => {
  it("SEND_MESSAGE adds a user message and sets streaming", () => {
    const state = chatReducer(initialChatState, {
      type: "SEND_MESSAGE",
      content: "Analyze AAPL",
    });
    expect(state.messages).toHaveLength(2);
    expect(state.messages[0].role).toBe("user");
    expect(state.messages[0].content).toBe("Analyze AAPL");
    expect(state.isStreaming).toBe(true);
  });

  it("SEND_MESSAGE adds empty assistant placeholder", () => {
    const state = chatReducer(initialChatState, {
      type: "SEND_MESSAGE",
      content: "Hi",
    });
    expect(state.messages).toHaveLength(2);
    expect(state.messages[1].role).toBe("assistant");
    expect(state.messages[1].content).toBe("");
    expect(state.messages[1].isStreaming).toBe(true);
  });

  it("FLUSH_TOKENS appends buffered content to last assistant message", () => {
    let state = chatReducer(initialChatState, {
      type: "SEND_MESSAGE",
      content: "Hi",
    });
    state = chatReducer(state, {
      type: "FLUSH_TOKENS",
      bufferedContent: "Hello ",
    });
    state = chatReducer(state, {
      type: "FLUSH_TOKENS",
      bufferedContent: "world",
    });
    expect(state.messages[1].content).toBe("Hello world");
  });

  it("TOOL_START adds a running tool call to the assistant message", () => {
    let state = chatReducer(initialChatState, {
      type: "SEND_MESSAGE",
      content: "Analyze AAPL",
    });
    state = chatReducer(state, {
      type: "TOOL_START",
      tool: "analyze_stock",
      params: { ticker: "AAPL" },
    });
    const toolCalls = state.messages[1].toolCalls;
    expect(toolCalls).toHaveLength(1);
    expect(toolCalls[0].status).toBe("running");
  });

  it("TOOL_RESULT updates the matching tool call to completed", () => {
    let state = chatReducer(initialChatState, {
      type: "SEND_MESSAGE",
      content: "Analyze AAPL",
    });
    state = chatReducer(state, {
      type: "TOOL_START",
      tool: "analyze_stock",
      params: { ticker: "AAPL" },
    });
    state = chatReducer(state, {
      type: "TOOL_RESULT",
      tool: "analyze_stock",
      status: "ok",
      data: { score: 7.2 },
    });
    expect(state.messages[1].toolCalls[0].status).toBe("completed");
    expect(state.messages[1].toolCalls[0].result).toEqual({ score: 7.2 });
  });

  it("STREAM_DONE marks streaming as false", () => {
    let state = chatReducer(initialChatState, {
      type: "SEND_MESSAGE",
      content: "Hi",
    });
    state = chatReducer(state, {
      type: "STREAM_DONE",
      usage: {},
    });
    expect(state.isStreaming).toBe(false);
    expect(state.messages[1].isStreaming).toBe(false);
  });

  it("STREAM_ERROR sets error and stops streaming", () => {
    let state = chatReducer(initialChatState, {
      type: "SEND_MESSAGE",
      content: "Hi",
    });
    state = chatReducer(state, {
      type: "STREAM_ERROR",
      error: "Connection lost",
    });
    expect(state.isStreaming).toBe(false);
    expect(state.error).toBe("Connection lost");
  });

  it("CLEAR resets to initial state", () => {
    let state = chatReducer(initialChatState, {
      type: "SEND_MESSAGE",
      content: "Hi",
    });
    state = chatReducer(state, { type: "CLEAR" });
    expect(state.messages).toHaveLength(0);
    expect(state.isStreaming).toBe(false);
  });
});
