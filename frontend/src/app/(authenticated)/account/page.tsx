"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  getAccountInfo,
  changePassword,
  setPassword,
  unlinkGoogle,
  getGoogleAuthUrl,
  resendVerification,
  deleteAccount,
} from "@/lib/api";
import type { AccountInfo } from "@/lib/api";

export default function AccountPage() {
  const queryClient = useQueryClient();
  const { data: account, isLoading } = useQuery<AccountInfo>({
    queryKey: ["account"],
    queryFn: getAccountInfo,
  });

  if (isLoading || !account) {
    return (
      <div className="max-w-2xl mx-auto">
        <h1 className="text-2xl font-bold text-foreground mb-6">Account Settings</h1>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-foreground">Account Settings</h1>
      <ProfileSection account={account} />
      <SecuritySection account={account} onUpdate={() => queryClient.invalidateQueries({ queryKey: ["account"] })} />
      <LinkedAccountsSection account={account} onUpdate={() => queryClient.invalidateQueries({ queryKey: ["account"] })} />
      <DangerZoneSection account={account} />
    </div>
  );
}

// --- Profile Section ---
function ProfileSection({ account }: { account: AccountInfo }) {
  const [sending, setSending] = useState(false);

  const handleResend = async () => {
    setSending(true);
    try {
      await resendVerification();
      toast.success("Verification email sent");
    } catch {
      toast.error("Failed to send verification email");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <h2 className="text-lg font-semibold text-foreground mb-4">Profile</h2>
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">Email</span>
          <span className="text-sm text-foreground">{account.email}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">Status</span>
          {account.email_verified ? (
            <span className="text-sm text-green-400">Verified</span>
          ) : (
            <div className="flex items-center gap-2">
              <span className="text-sm text-yellow-400">Unverified</span>
              <button
                onClick={handleResend}
                disabled={sending}
                className="text-xs text-primary hover:underline disabled:opacity-50"
              >
                {sending ? "Sending..." : "Resend"}
              </button>
            </div>
          )}
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">Member since</span>
          <span className="text-sm text-foreground">
            {new Date(account.created_at).toLocaleDateString()}
          </span>
        </div>
      </div>
    </div>
  );
}

// --- Security Section ---
function SecuritySection({
  account,
  onUpdate,
}: {
  account: AccountInfo;
  onUpdate: () => void;
}) {
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPw !== confirmPw) {
      toast.error("Passwords do not match");
      return;
    }
    setLoading(true);
    try {
      if (account.has_password) {
        await changePassword(currentPw, newPw);
      } else {
        await setPassword(newPw);
      }
      toast.success(account.has_password ? "Password changed" : "Password set");
      setCurrentPw("");
      setNewPw("");
      setConfirmPw("");
      onUpdate();
    } catch {
      toast.error("Failed to update password");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <h2 className="text-lg font-semibold text-foreground mb-4">Security</h2>
      <form onSubmit={handleSubmit} className="space-y-3">
        {account.has_password && (
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">
              Current password
            </label>
            <input
              type="password"
              required
              value={currentPw}
              onChange={(e) => setCurrentPw(e.target.value)}
              className="w-full rounded-lg border border-border bg-card2 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
        )}
        <div>
          <label className="block text-sm font-medium text-foreground mb-1">
            {account.has_password ? "New password" : "Set a password"}
          </label>
          <input
            type="password"
            required
            minLength={8}
            value={newPw}
            onChange={(e) => setNewPw(e.target.value)}
            className="w-full rounded-lg border border-border bg-card2 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            placeholder="Min 8 chars, 1 uppercase, 1 digit"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-foreground mb-1">
            Confirm password
          </label>
          <input
            type="password"
            required
            value={confirmPw}
            onChange={(e) => setConfirmPw(e.target.value)}
            className="w-full rounded-lg border border-border bg-card2 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
        >
          {loading
            ? "Saving..."
            : account.has_password
              ? "Change password"
              : "Set password"}
        </button>
      </form>
    </div>
  );
}

// --- Linked Accounts Section ---
function LinkedAccountsSection({
  account,
  onUpdate,
}: {
  account: AccountInfo;
  onUpdate: () => void;
}) {
  const [unlinking, setUnlinking] = useState(false);

  const handleUnlink = async () => {
    setUnlinking(true);
    try {
      await unlinkGoogle();
      toast.success("Google account unlinked");
      onUpdate();
    } catch {
      toast.error("Failed to unlink. Set a password first.");
    } finally {
      setUnlinking(false);
    }
  };

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <h2 className="text-lg font-semibold text-foreground mb-4">
        Linked Accounts
      </h2>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <svg className="h-5 w-5" viewBox="0 0 24 24">
            <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4" />
            <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
            <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18A10.96 10.96 0 0 0 1 12c0 1.77.42 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05" />
            <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
          </svg>
          <div>
            <p className="text-sm font-medium text-foreground">Google</p>
            {account.google_linked ? (
              <p className="text-xs text-muted-foreground">
                {account.google_email}
              </p>
            ) : (
              <p className="text-xs text-muted-foreground">Not connected</p>
            )}
          </div>
        </div>
        {account.google_linked ? (
          <button
            onClick={handleUnlink}
            disabled={unlinking || !account.has_password}
            title={!account.has_password ? "Set a password first" : undefined}
            className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-hov transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {unlinking ? "Unlinking..." : "Unlink"}
          </button>
        ) : (
          <a
            href={getGoogleAuthUrl("/account")}
            className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-hov transition-colors"
          >
            Link Google
          </a>
        )}
      </div>
    </div>
  );
}

// --- Danger Zone Section ---
function DangerZoneSection({ account }: { account: AccountInfo }) {
  const [showModal, setShowModal] = useState(false);
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [loading, setLoading] = useState(false);

  const handleDelete = async () => {
    if (confirmation !== "DELETE") {
      toast.error('Type "DELETE" to confirm');
      return;
    }
    setLoading(true);
    try {
      await deleteAccount(
        confirmation,
        account.has_password ? password : undefined
      );
      toast.success("Account scheduled for deletion");
      window.location.href = "/login";
    } catch {
      toast.error("Failed to delete account");
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="rounded-xl border border-red-900/50 bg-card p-6">
        <h2 className="text-lg font-semibold text-red-400 mb-2">
          Danger Zone
        </h2>
        <p className="text-sm text-muted-foreground mb-4">
          Permanently delete your account and all associated data. This action
          cannot be undone after 30 days.
        </p>
        <button
          onClick={() => setShowModal(true)}
          className="rounded-lg border border-red-700 px-4 py-2 text-sm font-medium text-red-400 hover:bg-red-900/20 transition-colors"
        >
          Delete account
        </button>
      </div>

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-md rounded-xl border border-border bg-card p-6 space-y-4">
            <h3 className="text-lg font-semibold text-foreground">
              Delete your account?
            </h3>
            <p className="text-sm text-muted-foreground">
              Your account will be deactivated immediately and permanently
              deleted after 30 days. All your portfolios, watchlists, and data
              will be removed.
            </p>
            {account.has_password && (
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">
                  Enter your password
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full rounded-lg border border-border bg-card2 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-red-500"
                />
              </div>
            )}
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">
                Type DELETE to confirm
              </label>
              <input
                type="text"
                value={confirmation}
                onChange={(e) => setConfirmation(e.target.value)}
                className="w-full rounded-lg border border-border bg-card2 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-red-500"
                placeholder="DELETE"
              />
            </div>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowModal(false)}
                className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-hov transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                disabled={loading || confirmation !== "DELETE"}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 transition-colors disabled:opacity-50"
              >
                {loading ? "Deleting..." : "Delete account"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
