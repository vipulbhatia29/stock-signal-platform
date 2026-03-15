import { cn } from "@/lib/utils";

const ACCENT_GRADIENTS = {
  cyan: "from-cyan to-transparent",
  gain: "from-gain to-transparent",
  loss: "from-loss to-transparent",
  warn: "from-warning to-transparent",
} as const;

interface StatTileProps {
  label: string;
  value?: string;
  sub?: React.ReactNode;
  onClick?: () => void;
  accentColor?: keyof typeof ACCENT_GRADIENTS;
  children?: React.ReactNode;
  className?: string;
}

export function StatTile({
  label,
  value,
  sub,
  onClick,
  accentColor = "cyan",
  children,
  className,
}: StatTileProps) {
  return (
    <div
      onClick={onClick}
      className={cn(
        "relative overflow-hidden rounded-[var(--radius)] border border-border bg-card p-[13px_14px]",
        "transition-colors hover:border-[var(--bhi)]",
        onClick && "cursor-pointer",
        className
      )}
    >
      {/* Top accent line */}
      <div
        className={cn(
          "absolute top-0 left-0 right-0 h-px bg-gradient-to-r",
          ACCENT_GRADIENTS[accentColor]
        )}
      />

      <div className="text-[9.5px] font-medium uppercase tracking-[0.09em] text-subtle mb-[5px]">
        {label}
      </div>

      {children ? (
        children
      ) : (
        <>
          {value && (
            <div className="font-mono text-[20px] font-bold tracking-tight leading-none text-foreground">
              {value}
            </div>
          )}
          {sub && <div className="mt-1.5 flex items-center gap-1.5">{sub}</div>}
        </>
      )}
    </div>
  );
}
