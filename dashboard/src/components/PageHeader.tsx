import { RefreshCw } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "../lib/format";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-7 flex flex-col gap-4 md:mb-9 md:flex-row md:items-end md:justify-between">
      <div className="max-w-2xl animate-fade-up">
        <p className="eyebrow mb-2">{eyebrow}</p>
        <h1 className="font-display text-[40px] leading-[0.98] tracking-[-0.02em] text-ink md:text-[54px]">
          {title}
        </h1>
        {description && (
          <p className="mt-3 max-w-xl text-[13px] leading-6 text-muted md:text-sm">
            {description}
          </p>
        )}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function RefreshButton({
  onClick,
  refreshing,
  label = "Refresh",
}: {
  onClick: () => void;
  refreshing?: boolean;
  label?: string;
}) {
  return (
    <button type="button" onClick={onClick} className="btn-secondary" disabled={refreshing}>
      <RefreshCw size={14} className={cn(refreshing && "animate-spin")} />
      {label}
    </button>
  );
}
