"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { resetPassword } from "@/lib/api";

export default function ResetPasswordPage() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [status, setStatus] = useState<"form" | "success" | "error">("form");
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirm) {
      setErrorMsg("Passwords do not match");
      return;
    }
    if (password.length < 8) {
      setErrorMsg("Password must be at least 8 characters");
      return;
    }
    setLoading(true);
    setErrorMsg("");
    try {
      await resetPassword(token, password);
      setStatus("success");
    } catch {
      setStatus("error");
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="w-full max-w-md rounded-xl border border-border bg-card p-8 text-center">
          <h2 className="text-xl font-semibold text-foreground mb-2">
            Invalid reset link
          </h2>
          <p className="text-muted-foreground mb-4">
            This password reset link is missing a token.
          </p>
          <a href="/auth/forgot-password" className="text-sm text-primary hover:underline">
            Request a new reset link
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="w-full max-w-md rounded-xl border border-border bg-card p-8">
        {status === "success" ? (
          <div className="text-center">
            <h2 className="text-xl font-semibold text-foreground mb-2">
              Password reset!
            </h2>
            <p className="text-muted-foreground mb-4">
              Your password has been updated. Please log in with your new
              password.
            </p>
            <a
              href="/login"
              className="inline-block rounded-lg bg-primary px-6 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              Go to Login
            </a>
          </div>
        ) : status === "error" ? (
          <div className="text-center">
            <h2 className="text-xl font-semibold text-foreground mb-2">
              Reset failed
            </h2>
            <p className="text-muted-foreground mb-4">
              This reset link is invalid or has expired.
            </p>
            <a href="/auth/forgot-password" className="text-sm text-primary hover:underline">
              Request a new reset link
            </a>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <h2 className="text-xl font-semibold text-foreground mb-2">
              Set new password
            </h2>
            {errorMsg && (
              <p className="text-sm text-red-400">{errorMsg}</p>
            )}
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-foreground mb-1">
                New password
              </label>
              <input
                id="password"
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg border border-border bg-card2 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                placeholder="Min 8 chars, 1 uppercase, 1 digit"
              />
            </div>
            <div>
              <label htmlFor="confirm" className="block text-sm font-medium text-foreground mb-1">
                Confirm password
              </label>
              <input
                id="confirm"
                type="password"
                required
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className="w-full rounded-lg border border-border bg-card2 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {loading ? "Resetting..." : "Reset password"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
