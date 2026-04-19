"use client";

import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthContext, useAuthProvider } from "@/lib/auth";
import { ErrorBoundary } from "@/components/error-boundary";
import { WindowErrorListeners } from "@/components/window-error-listeners";
import { reportError } from "@/lib/observability-beacon";
import { useState, type ReactNode } from "react";

function AuthProvider({ children }: { children: ReactNode }) {
  const auth = useAuthProvider();
  return <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>;
}

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000, // 1 minute
            retry: 1,
            refetchOnWindowFocus: false,
          },
          mutations: {
            onError: (error) => {
              reportError({
                error_type: "mutation_error",
                error_message: error instanceof Error ? error.message : String(error),
                page_route: typeof window !== "undefined" ? window.location.pathname : undefined,
              });
            },
          },
        },
        queryCache: new QueryCache({
          onError: (error) => {
            reportError({
              error_type: "query_error",
              error_message: error instanceof Error ? error.message : String(error),
              page_route: typeof window !== "undefined" ? window.location.pathname : undefined,
            });
          },
        }),
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider
        attribute="class"
        defaultTheme="dark"
        forcedTheme="dark"
        disableTransitionOnChange
      >
        <TooltipProvider>
          <ErrorBoundary>
            <AuthProvider>
              <WindowErrorListeners />
              {children}
              <Toaster />
            </AuthProvider>
          </ErrorBoundary>
        </TooltipProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
