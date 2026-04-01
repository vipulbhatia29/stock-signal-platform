import { cn } from "@/lib/utils";

interface HealthGradeBadgeProps {
  grade: string;
  score?: number;
  className?: string;
}

function getGradeColor(grade: string | undefined): string {
  if (!grade) return "bg-muted text-muted-foreground border-border";
  if (grade.startsWith("A")) return "bg-gain/15 text-[var(--gain)] border-gain/30";
  if (grade.startsWith("B")) return "bg-gain/10 text-[var(--gain)] border-gain/20";
  if (grade.startsWith("C")) return "bg-warning/15 text-[var(--warning)] border-warning/30";
  return "bg-loss/15 text-[var(--loss)] border-loss/30";
}

export function HealthGradeBadge({ grade, score, className }: HealthGradeBadgeProps) {
  return (
    <div className={cn(
      "inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5",
      getGradeColor(grade),
      className,
    )}>
      <span className="text-lg font-bold">{grade}</span>
      {score != null && <span className="text-xs opacity-75">{score.toFixed(1)}/10</span>}
    </div>
  );
}
