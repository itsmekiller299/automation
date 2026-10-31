import {
  ArrowUpRight,
  BrainCircuit,
  Inbox,
  LayoutDashboard,
  LifeBuoy,
  Menu,
  Settings,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { api } from "../lib/api";
import { usePolling } from "../lib/hooks";
import { cn } from "../lib/format";
import { Logo, SidebarStatus } from "./Logo";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/inbox", label: "Inbox", icon: Inbox },
  { to: "/handoffs", label: "Handoffs", icon: LifeBuoy },
  { to: "/model", label: "Model & learning", icon: BrainCircuit },
  { to: "/settings", label: "Settings", icon: Settings },
];

export default function Layout() {
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const ready = usePolling(api.ready, 60_000, []);
  const current = NAV.find(
    (item) => item.to === location.pathname || (!item.end && location.pathname.startsWith(item.to)),
  );

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  const statusDetail = ready.data
    ? `${ready.data.queue} queue · ${ready.data.nlu}`
    : ready.error
      ? "Backend unreachable"
      : "Connecting to the API…";

  const sidebar = (
    <div className="flex h-full flex-col bg-night px-4 pb-4 pt-6 text-paper">
      <div className="px-2">
        <Logo />
      </div>

      <nav className="mt-10 space-y-1">
        <p className="mb-3 px-3 text-[9px] font-bold uppercase tracking-[0.2em] text-paper/30">
          Workspace
        </p>
        {NAV.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  "group flex items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] font-semibold transition-all",
                  isActive
                    ? "bg-paper text-ink"
                    : "text-paper/55 hover:bg-paper/[0.06] hover:text-paper",
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Icon
                    size={16}
                    strokeWidth={isActive ? 2.1 : 1.7}
                    className={isActive ? "text-clay" : "text-paper/40 group-hover:text-paper/70"}
                  />
                  <span className="flex-1">{item.label}</span>
                  {isActive && <span className="h-1 w-1 rounded-full bg-clay" />}
                </>
              )}
            </NavLink>
          );
        })}
      </nav>

      <div className="mt-auto space-y-3">
        <a
          href="/portal"
          target="_blank"
          rel="noreferrer"
          className="flex items-center justify-between rounded-xl border border-paper/[0.09] px-3.5 py-2.5 text-[11px] font-semibold text-paper/55 transition-colors hover:border-paper/20 hover:text-paper"
        >
          Customer portal
          <ArrowUpRight size={13} />
        </a>
        <a
          href="/docs"
          target="_blank"
          rel="noreferrer"
          className="flex items-center justify-between rounded-xl border border-paper/[0.09] px-3.5 py-2.5 text-[11px] font-semibold text-paper/55 transition-colors hover:border-paper/20 hover:text-paper"
        >
          API reference
          <ArrowUpRight size={13} />
        </a>
        <SidebarStatus
          label={ready.data ? "System ready" : ready.error ? "Connection lost" : "Connecting"}
          detail={statusDetail}
          ready={Boolean(ready.data)}
        />
        <p className="px-2 text-[9px] leading-4 text-paper/25">
          Human-in-the-loop console.
          <br />
          Every handoff stays auditable.
        </p>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[248px] lg:block">{sidebar}</aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-night/55 backdrop-blur-sm"
            aria-label="Close navigation"
            onClick={() => setMobileOpen(false)}
          />
          <aside className="absolute inset-y-0 left-0 w-[270px] animate-fade-up shadow-lift">
            <button
              type="button"
              onClick={() => setMobileOpen(false)}
              className="absolute right-3 top-3 z-10 rounded-lg p-2 text-paper/60 hover:bg-paper/10 hover:text-paper"
              aria-label="Close navigation"
            >
              <X size={17} />
            </button>
            {sidebar}
          </aside>
        </div>
      )}

      <div className="lg:pl-[248px]">
        <div className="sticky top-0 z-20 border-b border-line/80 bg-paper/90 backdrop-blur-md">
          <div className="mx-auto flex h-14 max-w-[1500px] items-center justify-between gap-4 px-4 sm:px-6 lg:px-10">
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => setMobileOpen(true)}
                className="btn-ghost -ml-2 p-2 lg:hidden"
                aria-label="Open navigation"
              >
                <Menu size={18} />
              </button>
              <div className="flex items-center gap-2 text-[11px] font-semibold text-muted">
                <span className="hidden font-display text-base text-ink sm:inline">Orbit</span>
                <span className="hidden text-line-strong sm:inline">/</span>
                <span>{current?.label || "Workspace"}</span>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <span className="hidden items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-muted sm:flex">
                <span
                  className={cn(
                    "h-1.5 w-1.5 rounded-full",
                    ready.error ? "bg-danger" : "bg-moss animate-pulse-soft",
                  )}
                />
                {ready.error ? "Offline" : "Live"}
              </span>
              <span className="hidden text-[11px] text-muted md:inline">
                {new Intl.DateTimeFormat("en", {
                  weekday: "short",
                  day: "numeric",
                  month: "short",
                }).format(new Date())}
              </span>
              <span className="grid h-7 w-7 place-items-center rounded-full border border-line bg-panel text-[10px] font-bold text-ink-soft">
                AL
              </span>
            </div>
          </div>
        </div>

        <main className="mx-auto max-w-[1500px] px-4 py-7 sm:px-6 md:py-10 lg:px-10">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
