import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { Mail, Lock, User, ArrowRight, TrendingUp, BarChart3, Shield } from "lucide-react";
import logo from "@/assets/logo.png";

/* ── shared decorative left panel ── */
function BrandPanel() {
  return (
    <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden bg-gradient-to-br from-[hsl(var(--background))] via-[hsl(220,26%,11%)] to-[hsl(var(--background))] items-center justify-center p-12">
      {/* Animated grid background */}
      <div className="absolute inset-0 opacity-[0.04]"
        style={{
          backgroundImage: "linear-gradient(hsl(var(--primary)) 1px, transparent 1px), linear-gradient(90deg, hsl(var(--primary)) 1px, transparent 1px)",
          backgroundSize: "60px 60px",
        }}
      />

      {/* Glowing orbs */}
      <div className="absolute top-1/4 left-1/4 w-72 h-72 rounded-full bg-primary/10 blur-[120px]" />
      <div className="absolute bottom-1/4 right-1/4 w-56 h-56 rounded-full bg-primary/5 blur-[100px]" />

      <motion.div
        initial={{ opacity: 0, x: -30 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.7, ease: "easeOut" }}
        className="relative z-10 max-w-md space-y-10"
      >
        {/* Logo + brand */}
        <div className="flex items-center gap-3">
          <img src={logo} alt="Stock Signal logo" className="h-14 w-14 drop-shadow-[0_0_24px_hsl(var(--primary)/0.5)]" />
          <div>
            <h2 className="text-2xl font-bold tracking-tight text-foreground">Stock Signal</h2>
            <p className="text-xs text-muted-foreground tracking-widest uppercase">Intelligence Platform</p>
          </div>
        </div>

        {/* Feature bullets */}
        <div className="space-y-6">
          {[
            { icon: TrendingUp, title: "Real-time Signals", desc: "AI-powered buy/sell signals across 5 000+ stocks" },
            { icon: BarChart3, title: "Deep Analytics", desc: "Sector heat-maps, correlation matrices & custom screeners" },
            { icon: Shield, title: "Portfolio Guard", desc: "Risk scoring, allocation insights & smart alerts" },
          ].map((f, i) => (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 + i * 0.15 }}
              className="flex gap-4 items-start"
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 border border-primary/20">
                <f.icon className="h-5 w-5 text-primary" />
              </div>
              <div>
                <p className="text-sm font-semibold text-foreground">{f.title}</p>
                <p className="text-xs text-muted-foreground leading-relaxed">{f.desc}</p>
              </div>
            </motion.div>
          ))}
        </div>

        {/* Animated sparkline decoration */}
        <motion.div
          initial={{ scaleX: 0 }}
          animate={{ scaleX: 1 }}
          transition={{ delay: 0.8, duration: 1, ease: "easeOut" }}
          className="origin-left"
        >
          <svg viewBox="0 0 400 60" className="w-full h-12 text-primary/30">
            <polyline
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              points="0,45 30,40 60,42 90,30 120,35 150,20 180,25 210,10 240,15 270,8 300,12 330,5 360,8 400,2"
            />
            <linearGradient id="sparkGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity="0.15" />
              <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity="0" />
            </linearGradient>
            <polygon
              fill="url(#sparkGrad)"
              points="0,45 30,40 60,42 90,30 120,35 150,20 180,25 210,10 240,15 270,8 300,12 330,5 360,8 400,2 400,60 0,60"
            />
          </svg>
        </motion.div>
      </motion.div>
    </div>
  );
}

/* ── Google button ── */
function GoogleButton() {
  return (
    <button
      type="button"
      className="flex w-full items-center justify-center gap-3 rounded-lg border border-border bg-card2 py-2.5 text-sm font-medium text-foreground hover:bg-muted/60 transition-colors"
    >
      <svg className="h-4 w-4" viewBox="0 0 24 24">
        <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4" />
        <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
        <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18A10.96 10.96 0 0 0 1 12c0 1.77.42 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05" />
        <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
      </svg>
      Continue with Google
    </button>
  );
}

/* ── Divider ── */
function OrDivider() {
  return (
    <div className="flex items-center gap-3">
      <div className="h-px flex-1 bg-border" />
      <span className="text-[10px] uppercase tracking-widest text-muted-foreground">or</span>
      <div className="h-px flex-1 bg-border" />
    </div>
  );
}

/* ── Login ── */
export function Login() {
  return (
    <div className="flex min-h-screen bg-background">
      <BrandPanel />

      <div className="flex flex-1 items-center justify-center p-6">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="w-full max-w-sm space-y-6"
        >
          {/* Mobile logo */}
          <div className="flex items-center gap-3 lg:hidden mb-2">
            <img src={logo} alt="Stock Signal" className="h-10 w-10" />
            <span className="text-lg font-bold text-foreground">Stock Signal</span>
          </div>

          <div>
            <h1 className="text-2xl font-bold text-foreground">Welcome back</h1>
            <p className="mt-1 text-sm text-muted-foreground">Sign in to your account</p>
          </div>

          <div className="space-y-4">
            <GoogleButton />
            <OrDivider />
            <AuthInput icon={Mail} label="Email" type="email" placeholder="you@example.com" />
            <AuthInput icon={Lock} label="Password" type="password" placeholder="••••••••" />

            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
                <input type="checkbox" className="rounded border-border bg-card2 h-3.5 w-3.5 accent-primary" />
                Remember me
              </label>
              <a href="#" className="text-xs text-primary hover:underline">Forgot password?</a>
            </div>

            <button className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary py-2.5 text-sm font-semibold text-primary-foreground hover:brightness-110 transition-all shadow-[0_0_20px_hsl(var(--primary)/0.25)]">
              Sign in <ArrowRight className="h-4 w-4" />
            </button>
          </div>

          <p className="text-center text-xs text-muted-foreground">
            Don't have an account?{" "}
            <Link to="/register" className="text-primary font-medium hover:underline">Create one</Link>
          </p>
        </motion.div>
      </div>
    </div>
  );
}

/* ── Register ── */
export function Register() {
  return (
    <div className="flex min-h-screen bg-background">
      <BrandPanel />

      <div className="flex flex-1 items-center justify-center p-6">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="w-full max-w-sm space-y-6"
        >
          {/* Mobile logo */}
          <div className="flex items-center gap-3 lg:hidden mb-2">
            <img src={logo} alt="Stock Signal" className="h-10 w-10" />
            <span className="text-lg font-bold text-foreground">Stock Signal</span>
          </div>

          <div>
            <h1 className="text-2xl font-bold text-foreground">Create account</h1>
            <p className="mt-1 text-sm text-muted-foreground">Start your trading edge today</p>
          </div>

          <div className="space-y-4">
            <GoogleButton />
            <OrDivider />
            <AuthInput icon={User} label="Full name" type="text" placeholder="John Doe" />
            <AuthInput icon={Mail} label="Email" type="email" placeholder="you@example.com" />
            <AuthInput icon={Lock} label="Password" type="password" placeholder="••••••••" />

            <button className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary py-2.5 text-sm font-semibold text-primary-foreground hover:brightness-110 transition-all shadow-[0_0_20px_hsl(var(--primary)/0.25)]">
              Create account <ArrowRight className="h-4 w-4" />
            </button>
          </div>

          <p className="text-center text-xs text-muted-foreground">
            Already have an account?{" "}
            <Link to="/login" className="text-primary font-medium hover:underline">Sign in</Link>
          </p>
        </motion.div>
      </div>
    </div>
  );
}

/* ── Shared input ── */
function AuthInput({ icon: Icon, label, type, placeholder }: { icon: any; label: string; type: string; placeholder: string }) {
  return (
    <div>
      <label className="text-[10px] text-muted-foreground mb-1.5 block uppercase tracking-wider">{label}</label>
      <div className="flex items-center gap-2.5 rounded-lg border border-border bg-card2 px-3.5 py-2.5 focus-within:border-primary/50 focus-within:shadow-[0_0_0_2px_hsl(var(--primary)/0.1)] transition-all">
        <Icon className="h-4 w-4 text-muted-foreground" />
        <input
          type={type}
          placeholder={placeholder}
          className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none"
        />
      </div>
    </div>
  );
}
