// Centralized API client with cookie auth and auto-refresh on 401.
// All API calls in the app go through this module.

import type { ApiError } from "@/types/api";

const API_BASE = "/api/v1";

export class ApiRequestError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiRequestError";
    this.status = status;
    this.detail = detail;
  }
}

async function refreshToken(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    return res.ok;
  } catch {
    return false;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE}${path}`;

  const config: RequestInit = {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  };

  let res = await fetch(url, config);

  // Auto-refresh on 401 and retry once
  if (res.status === 401) {
    const refreshed = await refreshToken();
    if (refreshed) {
      res = await fetch(url, config);
    }
  }

  if (!res.ok) {
    let detail = `Request failed with status ${res.status}`;
    try {
      const body: ApiError = await res.json();
      detail = body.detail || detail;
    } catch {
      // Response body wasn't JSON
    }

    // Redirect to login on auth failure after refresh attempt
    if (res.status === 401 && typeof window !== "undefined") {
      window.location.href = "/login";
    }

    throw new ApiRequestError(res.status, detail);
  }

  // Handle 204 No Content
  if (res.status === 204) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}

// ── HTTP method helpers ───────────────────────────────────────────────────────

export function get<T>(path: string): Promise<T> {
  return request<T>(path, { method: "GET" });
}

export function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: body ? JSON.stringify(body) : undefined,
  });
}

export function del<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

// ── Auth (no auto-redirect on failure) ────────────────────────────────────────

export async function loginRequest(
  email: string,
  password: string
): Promise<void> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });

  if (!res.ok) {
    let detail = "Login failed";
    try {
      const body: ApiError = await res.json();
      detail = body.detail || detail;
    } catch {
      // not JSON
    }
    throw new ApiRequestError(res.status, detail);
  }
}

export async function registerRequest(
  email: string,
  password: string
): Promise<void> {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });

  if (!res.ok) {
    let detail = "Registration failed";
    try {
      const body: ApiError = await res.json();
      detail = body.detail || detail;
    } catch {
      // not JSON
    }
    throw new ApiRequestError(res.status, detail);
  }
}

export async function logoutRequest(): Promise<void> {
  await fetch(`${API_BASE}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
}
