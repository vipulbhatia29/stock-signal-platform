"use client";

import { useState } from "react";
import { useCurrentUser } from "@/hooks/use-current-user";
import { resendVerification } from "@/lib/api";
import { toast } from "sonner";

export function EmailVerificationBanner() {
  const { data: user } = useCurrentUser();
  const [sending, setSending] = useState(false);

  // Don't show if user data not loaded or email already verified
  if (!user || user.email_verified !== false) return null;

  const handleResend = async () => {
    setSending(true);
    try {
      await resendVerification();
      toast.success("Verification email sent! Check your inbox.");
    } catch {
      toast.error("Failed to send verification email");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="bg-yellow-900/30 border-b border-yellow-700/50 px-4 py-2 flex items-center justify-between">
      <p className="text-sm text-yellow-200">
        Please verify your email to unlock all features.
      </p>
      <button
        onClick={handleResend}
        disabled={sending}
        className="text-sm font-medium text-yellow-100 hover:text-white underline disabled:opacity-50"
      >
        {sending ? "Sending..." : "Resend verification email"}
      </button>
    </div>
  );
}
