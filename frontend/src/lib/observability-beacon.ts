/**
 * Frontend observability beacon — batches JavaScript errors and sends them
 * to the backend via navigator.sendBeacon() (survives page unload) with
 * fetch() fallback.
 *
 * Usage: import { reportError } from "@/lib/observability-beacon";
 */

export interface FrontendErrorItem {
  error_type: string;
  error_message?: string;
  error_stack?: string;
  page_route?: string;
  component_name?: string;
  url?: string;
  metadata?: Record<string, unknown>;
}

const BATCH_INTERVAL_MS = 5000;
const MAX_BATCH_SIZE = 10;
const MAX_BUFFER_SIZE = 100;

const errorBuffer: FrontendErrorItem[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;

export function reportError(item: FrontendErrorItem): void {
  if (errorBuffer.length >= MAX_BUFFER_SIZE) {
    errorBuffer.shift(); // Drop oldest to prevent unbounded growth
  }
  errorBuffer.push(item);
  if (errorBuffer.length >= MAX_BATCH_SIZE) {
    flush();
  } else if (!flushTimer) {
    flushTimer = setTimeout(flush, BATCH_INTERVAL_MS);
  }
}

function flush(): void {
  if (errorBuffer.length === 0) return;
  const batch = errorBuffer.splice(0, MAX_BATCH_SIZE);
  const payload = JSON.stringify({ errors: batch });
  const url = "/api/v1/observability/frontend-error";

  // Include X-Trace-Id from last API response if available
  const traceId = (window as unknown as Record<string, unknown>).__lastTraceId as
    | string
    | undefined;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (traceId) {
    headers["X-Trace-Id"] = traceId;
  }

  const blob = new Blob([payload], { type: "application/json" });
  if (navigator.sendBeacon) {
    navigator.sendBeacon(url, blob);
  } else {
    fetch(url, {
      method: "POST",
      body: payload,
      headers,
      keepalive: true,
    }).catch(() => {}); // fire-and-forget
  }

  if (flushTimer) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }
}

// Flush on page visibility change (covers tab close, navigation)
if (typeof window !== "undefined") {
  window.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") flush();
  });
}
