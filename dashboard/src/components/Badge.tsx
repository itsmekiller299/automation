import type { ReactNode } from "react";

import { cn } from "../lib/format";

export function Badge({
  children,
  tone = "neutral",
  dot = false,
  className,
}: {
  children: ReactNode;
  tone?: "neutral" | "clay" | "moss" | "amber" | "danger" | "violet";
  dot?: boolean;
  className?: string;
}) {
  const tones = {
    neutral: "border-line bg-paper text-ink-soft",
    clay: "border-clay/20 bg-clay-soft text-clay",
    moss: "border-moss/15 bg-moss-soft text-moss",
    amber: "border-amber/20 bg-amber-soft text-amber",
    danger: "border-danger/20 bg-danger-soft text-danger",
    violet: "border-[#5B487E]/15 bg-[#E6E1F0] text-[#5B487E]",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.06em]",
        tones[tone],
        className,
      )}
    >
      {dot && <span className="h-1 w-1 rounded-full bg-current" />}
      {children}
    </span>
  );
}
