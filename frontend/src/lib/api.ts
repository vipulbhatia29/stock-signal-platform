// Centralized API client with cookie auth and auto-refresh on 401.
// All API calls in the app go through this module.

import type { ApiError } from "@/types/api";

const API_BASE = "/api/v1";

function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith("csrf_token="));
  return match ? match.split("=")[1] : null;
}

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

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  // Attach CSRF token for mutating requests (cookie-auth only)
  const method = (options.method || "GET").toUpperCase();
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    const csrfToken = getCsrfToken();
    if (csrfToken) {
      headers["X-CSRF-Token"] = csrfToken;
    }
  }

  const config: RequestInit = {
    ...options,
    credentials: "include",
    headers,
  };

  let res = await fetch(url, config);

  // Capture X-Trace-Id from response for observability beacon
  const traceId = res.headers.get("X-Trace-Id");
  if (traceId) {
    (window as unknown as Record<string, unknown>).__lastTraceId = traceId;
  }

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

export function patch<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "PATCH",
    body: body ? JSON.stringify(body) : undefined,
  });
}

export function del<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

export async function postMultipart<T>(path: string, formData: FormData): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    method: "POST",
    credentials: "include",
    body: formData,
    // Do NOT set Content-Type — browser sets it with boundary automatically
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiRequestError(res.status, body.detail || res.statusText);
  }
  return res.json();
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

// --- Google OAuth ---
export function getGoogleAuthUrl(next?: string): string {
  const params = next ? `?next=${encodeURIComponent(next)}` : "";
  return `${API_BASE}/auth/google/authorize${params}`;
}

// --- Email Verification ---
export function verifyEmail(token: string): Promise<void> {
  return post("/auth/verify-email", { token });
}

export function resendVerification(): Promise<void> {
  return post("/auth/resend-verification");
}

// --- Password Reset ---
export function forgotPassword(email: string): Promise<void> {
  return post("/auth/forgot-password", { email });
}

export function resetPassword(
  token: string,
  newPassword: string
): Promise<void> {
  return post("/auth/reset-password", { token, new_password: newPassword });
}

// --- Account Settings ---
export interface AccountInfo {
  id: string;
  email: string;
  email_verified: boolean;
  has_password: boolean;
  google_linked: boolean;
  google_email: string | null;
  created_at: string;
}

export function getAccountInfo(): Promise<AccountInfo> {
  return get("/auth/account");
}

export function changePassword(
  currentPassword: string,
  newPassword: string
): Promise<void> {
  return post("/auth/change-password", {
    current_password: currentPassword,
    new_password: newPassword,
  });
}

export function setPassword(newPassword: string): Promise<void> {
  return post("/auth/set-password", { new_password: newPassword });
}

export function unlinkGoogle(): Promise<void> {
  return post("/auth/google/unlink");
}

export function deleteAccount(
  confirmation: string,
  password?: string
): Promise<void> {
  return post("/auth/delete-account", {
    confirmation,
    password: password ?? null,
  });
}
