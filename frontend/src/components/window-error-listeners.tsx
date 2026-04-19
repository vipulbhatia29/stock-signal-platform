"use client";

import { useEffect } from "react";
import { reportError } from "@/lib/observability-beacon";

/**
 * Side-effect-only component that registers global window error and
 * unhandledrejection listeners. Renders nothing.
 *
 * Must be rendered inside a Client Component (not layout.tsx which
 * may be a Server Component).
 */
export function WindowErrorListeners() {
  useEffect(() => {
    const onError = (e: ErrorEvent) => {
      reportError({
        error_type: "window_error",
        error_message: e.message,
        error_stack: e.error?.stack?.slice(0, 5120),
        page_route: window.location.pathname,
        url: e.filename,
      });
    };
    const onUnhandledRejection = (e: PromiseRejectionEvent) => {
      reportError({
        error_type: "unhandled_rejection",
        error_message: String(e.reason),
        page_route: window.location.pathname,
      });
    };
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onUnhandledRejection);
    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onUnhandledRejection);
    };
  }, []);
  return null;
}
