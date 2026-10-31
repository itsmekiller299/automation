import { Link } from "react-router-dom";

import { cn } from "../lib/format";

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <Link to="/" className="group flex items-center gap-3" aria-label="Orbit dashboard">
      <span className="relative grid h-10 w-10 place-items-center rounded-full border border-paper/20 bg-paper/[0.06]">
        <span className="absolute inset-[5px] rounded-full border border-clay/70" />
        <span className="absolute right-[2px] top-[13px] h-1.5 w-1.5 rounded-full bg-clay" />
        <span className="font-display text-xl leading-none text-paper">O</span>
      </span>
      {!compact && (
        <span className="leading-none">
          <span className="block font-display text-[24px] tracking-tight text-paper">
            Orbit
          </span>
          <span className="mt-1 block text-[9px] font-semibold uppercase tracking-[0.22em] text-paper/40">
            Aurora Living
          </span>
        </span>
      )}
    </Link>
  );
}

export function SidebarStatus({
  label,
  detail,
  ready,
}: {
  label: string;
  detail: string;
  ready: boolean;
}) {
  return (
    <div className="rounded-2xl border border-paper/[0.09] bg-paper/[0.035] p-3.5">
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "h-1.5 w-1.5 rounded-full",
            ready ? "bg-[#9AC7A5] animate-pulse-soft" : "bg-[#C97A63]",
          )}
        />
        <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-paper/60">
          {label}
        </span>
      </div>
      <p className="mt-2 text-[12px] font-medium leading-4 text-paper/80">{detail}</p>
    </div>
  );
}
