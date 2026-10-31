import { AlertTriangle, Inbox, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import type { ReactNode } from "react";

import { cn } from "../lib/format";

export function SectionCard({
  title,
  eyebrow,
  action,
  children,
  className,
  bodyClassName,
}: {
  title?: string;
  eyebrow?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cn("surface overflow-hidden", className)}>
      {(title || eyebrow || action) && (
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div>
            {eyebrow && <p className="eyebrow mb-1">{eyebrow}</p>}
            {title && (
              <h2 className="font-display text-[24px] leading-tight tracking-tight text-ink">
                {title}
              </h2>
            )}
          </div>
          {action}
        </div>
      )}
      <div className={cn("p-5", bodyClassName)}>{children}</div>
    </section>
  );
}

export function EmptyState({
  title,
  description,
  icon: Icon = Inbox,
  action,
  compact = false,
}: {
  title: string;
  description?: string;
  icon?: typeof Inbox;
  action?: ReactNode;
  compact?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center",
        compact ? "py-8" : "py-14",
      )}
    >
      <span className="grid h-11 w-11 place-items-center rounded-full border border-line bg-paper text-muted">
        <Icon size={18} strokeWidth={1.6} />
      </span>
      <p className="mt-4 text-sm font-semibold text-ink">{title}</p>
      {description && (
        <p className="mt-1.5 max-w-sm text-[12px] leading-5 text-muted">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
}: {
  error: Error;
  onRetry?: () => void;
}) {
  const unauthorized = error.message.toLowerCase().includes("x-api-key") || error.message.includes("401");
  return (
    <div className="surface flex flex-col items-start gap-4 border-danger/20 bg-danger-soft/40 p-6">
      <span className="grid h-10 w-10 place-items-center rounded-full bg-danger-soft text-danger">
        <AlertTriangle size={17} />
      </span>
      <div>
        <p className="text-sm font-semibold text-ink">
          {unauthorized ? "Admin API key required" : "Something interrupted the signal"}
        </p>
        <p className="mt-1 max-w-xl text-[12px] leading-5 text-muted">
          {unauthorized
            ? "Add the ADMIN_API_KEY from your .env in Settings, then refresh this view."
            : error.message}
        </p>
      </div>
      <div className="flex gap-2">
        {unauthorized && (
          <Link to="/settings" className="btn-primary">
            Open settings
          </Link>
        )}
        {onRetry && (
          <button type="button" onClick={onRetry} className="btn-secondary">
            <RefreshCw size={13} /> Try again
          </button>
        )}
      </div>
    </div>
  );
}

export function SkeletonRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, index) => (
        <div
          key={index}
          className="h-12 animate-pulse rounded-xl bg-line/45"
          style={{ animationDelay: `${index * 70}ms` }}
        />
      ))}
    </div>
  );
}
