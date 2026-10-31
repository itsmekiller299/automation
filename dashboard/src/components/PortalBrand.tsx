import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { cn } from "../lib/format";

export function PortalBrand({ compact = false }: { compact?: boolean }) {
  return (
    <Link to="/portal" className="group flex items-center gap-3" aria-label="Orbit portal">
      <span className="relative grid h-9 w-9 place-items-center rounded-full border border-ink/15 bg-panel">
        <span className="absolute inset-[5px] rounded-full border border-clay/60" />
        <span className="absolute right-[2px] top-[11px] h-1.5 w-1.5 rounded-full bg-clay" />
        <span className="font-display text-lg leading-none text-ink">O</span>
      </span>
      {!compact && (
        <span className="leading-none">
          <span className="block font-display text-[22px] tracking-tight text-ink">Orbit</span>
          <span className="mt-1 block text-[9px] font-semibold uppercase tracking-[0.22em] text-muted">
            Customer portal
          </span>
        </span>
      )}
    </Link>
  );
}

export function PortalFrame({
  children,
  aside,
  wide = false,
}: {
  children: ReactNode;
  aside?: ReactNode;
  wide?: boolean;
}) {
  return (
    <div className="min-h-screen bg-paper">
      <div className="mx-auto flex min-h-screen max-w-[1440px] flex-col px-4 sm:px-6 lg:px-10">
        <header className="flex h-[76px] shrink-0 items-center justify-between gap-4">
          <PortalBrand />
          {aside}
        </header>
        <main className={cn("flex-1 pb-10", wide ? "" : "flex items-center py-6")}>
          {children}
        </main>
        <footer className="flex flex-col gap-2 border-t border-line py-5 text-[10px] leading-4 text-muted sm:flex-row sm:items-center sm:justify-between">
          <p>
            Orbit runs on Meta&apos;s official Cloud API and Messaging API. We never ask for
            your Instagram or WhatsApp password.
          </p>
          <a
            href="/"
            className="font-semibold uppercase tracking-[0.1em] text-muted transition-colors hover:text-ink"
          >
            Operations console
          </a>
        </footer>
      </div>
    </div>
  );
}
