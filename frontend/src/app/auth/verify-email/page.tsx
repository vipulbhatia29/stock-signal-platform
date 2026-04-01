"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { verifyEmail } from "@/lib/api";

export default function VerifyEmailPage() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";
  const [status, setStatus] = useState<"loading" | "success" | "error">(
    token ? "loading" : "error"
  );

  useEffect(() => {
    if (!token) return;
    verifyEmail(token)
      .then(() => setStatus("success"))
      .catch(() => setStatus("error"));
  }, [token]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="w-full max-w-md rounded-xl border border-border bg-card p-8 text-center">
        {status === "loading" && (
          <p className="text-muted-foreground">Verifying your email...</p>
        )}
        {status === "success" && (
          <>
            <h2 className="text-xl font-semibold text-foreground mb-2">
              Email verified!
            </h2>
            <p className="text-muted-foreground mb-4">
              Your email has been verified. You can now access all features.
            </p>
            <a
              href="/login"
              className="inline-block rounded-lg bg-primary px-6 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              Go to Login
            </a>
          </>
        )}
        {status === "error" && (
          <>
            <h2 className="text-xl font-semibold text-foreground mb-2">
              Invalid or expired link
            </h2>
            <p className="text-muted-foreground mb-4">
              This verification link is invalid or has expired. Please request a
              new one from your account settings.
            </p>
            <a
              href="/login"
              className="inline-block rounded-lg bg-primary px-6 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              Go to Login
            </a>
          </>
        )}
      </div>
    </div>
  );
}
