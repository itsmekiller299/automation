import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "../lib/format";

export function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  tone = "neutral",
  className,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: LucideIcon;
  tone?: "neutral" | "clay" | "moss" | "amber" | "danger";
  className?: string;
}) {
  const tones = {
    neutral: "bg-ink/[0.045] text-ink-soft",
    clay: "bg-clay-soft text-clay",
    moss: "bg-moss-soft text-moss",
    amber: "bg-amber-soft text-amber",
    danger: "bg-danger-soft text-danger",
  };

  return (
    <div
      className={cn(
        "surface relative overflow-hidden p-5 transition-colors hover:border-line-strong",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <p className="eyebrow">{label}</p>
        {Icon && (
          <span className={cn("rounded-lg p-1.5", tones[tone])}>
            <Icon size={14} strokeWidth={1.8} />
          </span>
        )}
      </div>
      <p className="mt-5 font-display text-[38px] leading-none tracking-tight text-ink">
        {value}
      </p>
      {hint && <div className="mt-3 text-[11px] leading-4 text-muted">{hint}</div>}
    </div>
  );
}
