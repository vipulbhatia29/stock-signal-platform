import { parseNDJSONLines } from "../ndjson-parser";

describe("parseNDJSONLines", () => {
  it("parses a complete single line", () => {
    const { events, remainder } = parseNDJSONLines(
      '{"type":"token","content":"hello"}\n',
      ""
    );
    expect(events).toHaveLength(1);
    expect(events[0].type).toBe("token");
    expect(events[0].content).toBe("hello");
    expect(remainder).toBe("");
  });

  it("handles multiple lines in one chunk", () => {
    const { events, remainder } = parseNDJSONLines(
      '{"type":"thinking","content":"..."}\n{"type":"token","content":"Hi"}\n',
      ""
    );
    expect(events).toHaveLength(2);
    expect(events[0].type).toBe("thinking");
    expect(events[1].type).toBe("token");
    expect(remainder).toBe("");
  });

  it("buffers incomplete line across chunks", () => {
    const { events: events1, remainder: rem1 } = parseNDJSONLines(
      '{"type":"tok',
      ""
    );
    expect(events1).toHaveLength(0);
    expect(rem1).toBe('{"type":"tok');

    const { events: events2, remainder: rem2 } = parseNDJSONLines(
      'en","content":"hi"}\n',
      rem1
    );
    expect(events2).toHaveLength(1);
    expect(events2[0].type).toBe("token");
    expect(rem2).toBe("");
  });

  it("skips empty lines", () => {
    const { events } = parseNDJSONLines(
      '\n\n{"type":"done"}\n\n',
      ""
    );
    expect(events).toHaveLength(1);
    expect(events[0].type).toBe("done");
  });

  it("skips malformed lines and continues", () => {
    const warnSpy = jest.spyOn(console, "warn").mockImplementation();
    const { events } = parseNDJSONLines(
      'not json\n{"type":"token","content":"ok"}\n',
      ""
    );
    expect(events).toHaveLength(1);
    expect(events[0].content).toBe("ok");
    expect(warnSpy).toHaveBeenCalledTimes(1);
    warnSpy.mockRestore();
  });
});
