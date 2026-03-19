import type { StreamEvent } from "@/types/api";

/**
 * Parse an NDJSON chunk with buffer carry-over.
 *
 * Splits on newlines, parses complete JSON lines, carries
 * incomplete trailing data as the remainder for the next chunk.
 * Malformed lines are logged and skipped.
 */
export function parseNDJSONLines(
  chunk: string,
  previousBuffer: string
): { events: StreamEvent[]; remainder: string } {
  const combined = previousBuffer + chunk;
  const lines = combined.split("\n");
  const remainder = lines.pop() ?? "";
  const events: StreamEvent[] = [];

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      events.push(JSON.parse(trimmed) as StreamEvent);
    } catch {
      console.warn("[NDJSON] Malformed line:", trimmed);
    }
  }

  return { events, remainder };
}
