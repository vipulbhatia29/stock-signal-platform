"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { Mail, Lock, User, ArrowRight, TrendingUp, BarChart3, Shield } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";

function BrandPanel() {
  return (
    <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden bg-gradient-to-br from-background via-card to-background items-center justify-center p-12">
      <div
        className="absolute inset-0 opacity-[0.04]"
        style={{
          backgroundImage:
            "linear-gradient(var(--cyan) 1px, transparent 1px), linear-gradient(90deg, var(--cyan) 1px, transparent 1px)",
          backgroundSize: "60px 60px",
        }}
      />
      <div className="absolute top-1/4 left-1/4 w-72 h-72 rounded-full bg-cyan/10 blur-[120px]" />
      <div className="absolute bottom-1/4 right-1/4 w-56 h-56 rounded-full bg-cyan/5 blur-[100px]" />

      <div className="relative z-10 max-w-md space-y-10">
        <div className="flex items-center gap-3">
          <div
            className="w-14 h-14 rounded-xl bg-cyan flex items-center justify-center"
            style={{ boxShadow: "0 0 24px var(--cg)" }}
          >
            <span className="text-[var(--background)] font-bold text-2xl">S</span>
          </div>
          <div>
            <h2 className="text-2xl font-bold tracking-tight text-foreground">Stock Signal</h2>
            <p className="text-xs text-muted-foreground tracking-widest uppercase">Intelligence Platform</p>
          </div>
        </div>

        <div className="space-y-6">
          {[
            { icon: TrendingUp, title: "Real-time Signals", desc: "AI-powered buy/sell signals across 5 000+ stocks" },
            { icon: BarChart3, title: "Deep Analytics", desc: "Sector heat-maps, correlation matrices & custom screeners" },
            { icon: Shield, title: "Portfolio Guard", desc: "Risk scoring, allocation insights & smart alerts" },
          ].map((f) => (
            <div key={f.title} className="flex gap-4 items-start">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[var(--cdim)] border border-[var(--bhi)]">
                <f.icon className="h-5 w-5 text-cyan" />
              </div>
              <div>
                <p className="text-sm font-semibold text-foreground">{f.title}</p>
                <p className="text-xs text-muted-foreground leading-relaxed">{f.desc}</p>
              </div>
            </div>
          ))}
        </div>

        <svg viewBox="0 0 400 60" className="w-full h-12 text-cyan/30">
          <polyline fill="none" stroke="currentColor" strokeWidth="2" points="0,45 30,40 60,42 90,30 120,35 150,20 180,25 210,10 240,15 270,8 300,12 330,5 360,8 400,2" />
          <defs>
            <linearGradient id="sparkGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--cyan)" stopOpacity="0.15" />
              <stop offset="100%" stopColor="var(--cyan)" stopOpacity="0" />
            </linearGradient>
          </defs>
          <polygon fill="url(#sparkGrad)" points="0,45 30,40 60,42 90,30 120,35 150,20 180,25 210,10 240,15 270,8 300,12 330,5 360,8 400,2 400,60 0,60" />
        </svg>
      </div>
    </div>
  );
}

export default function RegisterPage() {
  const { register, isLoading, error, clearError } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setLocalError(null);

    if (password.length < 8) {
      setLocalError("Password must be at least 8 characters");
      return;
    }

    await register(email, password);
  }

  const displayError = localError || error;

  return (
    <div className="flex min-h-screen bg-background">
      <BrandPanel />

      <div className="flex flex-1 items-center justify-center p-6">
        <div className="w-full max-w-sm space-y-6">
          {/* Mobile logo */}
          <div className="flex items-center gap-3 lg:hidden mb-2">
            <div className="w-10 h-10 rounded-lg bg-cyan flex items-center justify-center" style={{ boxShadow: "0 0 18px var(--cg)" }}>
              <span className="text-[var(--background)] font-bold text-lg">S</span>
            </div>
            <span className="text-lg font-bold text-foreground">Stock Signal</span>
          </div>

          <div>
            <h1 className="text-2xl font-bold text-foreground">Create account</h1>
            <p className="mt-1 text-sm text-muted-foreground">Start your trading edge today</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <button
              type="button"
              onClick={() => toast.info("Google OAuth coming soon")}
              className="flex w-full items-center justify-center gap-3 rounded-lg border border-border bg-card2 py-2.5 text-sm font-medium text-foreground hover:bg-hov transition-colors"
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24">
                <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4" />
                <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18A10.96 10.96 0 0 0 1 12c0 1.77.42 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05" />
                <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
              </svg>
              Continue with Google
            </button>

            <div className="flex items-center gap-3">
              <div className="h-px flex-1 bg-border" />
              <span className="text-[10px] uppercase tracking-widest text-muted-foreground">or</span>
              <div className="h-px flex-1 bg-border" />
            </div>

            {displayError && (
              <div
                className="rounded-md bg-destructive/10 p-3 text-sm text-destructive cursor-pointer"
                onClick={() => { setLocalError(null); clearError(); }}
              >
                {displayError}
              </div>
            )}

            {/* Full name */}
            <div>
              <label className="text-[10px] text-muted-foreground mb-1.5 block uppercase tracking-wider">Full name</label>
              <div className="flex items-center gap-2.5 rounded-lg border border-border bg-card2 px-3.5 py-2.5 focus-within:border-[var(--bhi)] focus-within:shadow-[0_0_0_2px_var(--cyan-muted)] transition-all">
                <User className="h-4 w-4 text-muted-foreground" />
                <input
                  type="text"
                  placeholder="John Doe"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none"
                />
              </div>
            </div>

            {/* Email */}
            <div>
              <label className="text-[10px] text-muted-foreground mb-1.5 block uppercase tracking-wider">Email</label>
              <div className="flex items-center gap-2.5 rounded-lg border border-border bg-card2 px-3.5 py-2.5 focus-within:border-[var(--bhi)] focus-within:shadow-[0_0_0_2px_var(--cyan-muted)] transition-all">
                <Mail className="h-4 w-4 text-muted-foreground" />
                <input
                  type="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="email"
                  className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none"
                />
              </div>
            </div>

            {/* Password */}
            <div>
              <label className="text-[10px] text-muted-foreground mb-1.5 block uppercase tracking-wider">Password</label>
              <div className="flex items-center gap-2.5 rounded-lg border border-border bg-card2 px-3.5 py-2.5 focus-within:border-[var(--bhi)] focus-within:shadow-[0_0_0_2px_var(--cyan-muted)] transition-all">
                <Lock className="h-4 w-4 text-muted-foreground" />
                <input
                  type="password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="new-password"
                  className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-cyan py-2.5 text-sm font-semibold text-[var(--background)] hover:brightness-110 transition-all shadow-[0_0_20px_var(--cyan-muted)] disabled:opacity-50"
            >
              {isLoading ? "Creating account..." : "Create account"} <ArrowRight className="h-4 w-4" />
            </button>
          </form>

          <p className="text-center text-xs text-muted-foreground">
            Already have an account?{" "}
            <Link href="/login" className="text-cyan font-medium hover:underline">Sign in</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
