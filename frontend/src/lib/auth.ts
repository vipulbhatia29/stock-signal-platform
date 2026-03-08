"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import {
  loginRequest,
  logoutRequest,
  registerRequest,
  ApiRequestError,
} from "@/lib/api";

interface AuthContextValue {
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  clearError: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}

export function useAuthProvider(): AuthContextValue {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  const login = useCallback(
    async (email: string, password: string) => {
      setIsLoading(true);
      setError(null);
      try {
        await loginRequest(email, password);
        setIsAuthenticated(true);
        router.push("/dashboard");
      } catch (err) {
        const message =
          err instanceof ApiRequestError ? err.detail : "Login failed";
        setError(message);
      } finally {
        setIsLoading(false);
      }
    },
    [router]
  );

  const register = useCallback(
    async (email: string, password: string) => {
      setIsLoading(true);
      setError(null);
      try {
        await registerRequest(email, password);
        router.push("/login");
      } catch (err) {
        const message =
          err instanceof ApiRequestError ? err.detail : "Registration failed";
        setError(message);
      } finally {
        setIsLoading(false);
      }
    },
    [router]
  );

  const logout = useCallback(async () => {
    await logoutRequest();
    setIsAuthenticated(false);
    router.push("/login");
  }, [router]);

  const clearError = useCallback(() => setError(null), []);

  return useMemo(
    () => ({
      isAuthenticated,
      isLoading,
      error,
      login,
      register,
      logout,
      clearError,
    }),
    [isAuthenticated, isLoading, error, login, register, logout, clearError]
  );
}
