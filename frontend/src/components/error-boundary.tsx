"use client";

import { Component, type ReactNode } from "react";
import { reportError } from "@/lib/observability-beacon";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    reportError({
      error_type: "react_error_boundary",
      error_message: error.message,
      error_stack: (error.stack || "").slice(0, 5120),
      component_name:
        info.componentStack?.split("\n")[1]?.trim() || undefined,
      page_route:
        typeof window !== "undefined"
          ? window.location.pathname
          : undefined,
    });
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex items-center justify-center min-h-screen">
          <div className="text-center">
            <h2 className="text-xl font-semibold mb-2">
              Something went wrong
            </h2>
            <button
              onClick={() => this.setState({ hasError: false })}
              className="text-blue-400 underline"
            >
              Try again
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
