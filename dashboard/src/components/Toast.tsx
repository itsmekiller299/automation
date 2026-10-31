import { AlertTriangle, Check, Info, X } from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { cn } from "../lib/format";

type Tone = "success" | "error" | "info";

interface ToastItem {
  id: string;
  message: string;
  tone: Tone;
}

interface ToastContextValue {
  push: (message: string, tone?: Tone) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const ICONS = {
  success: Check,
  error: AlertTriangle,
  info: Info,
};

const TONES = {
  success: "border-moss/30 bg-moss-soft text-moss",
  error: "border-danger/30 bg-danger-soft text-danger",
  info: "border-line bg-paper text-ink-soft",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const remove = useCallback((id: string) => {
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);

  const push = useCallback(
    (message: string, tone: Tone = "success") => {
      const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
      setItems((current) => [...current.slice(-3), { id, message, tone }]);
      window.setTimeout(() => remove(id), 4200);
    },
    [remove],
  );

  const value = useMemo(() => ({ push }), [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="pointer-events-none fixed bottom-5 right-5 z-[80] flex w-[min(360px,calc(100vw-2.5rem))] flex-col gap-2"
        aria-live="polite"
      >
        {items.map((item) => {
          const Icon = ICONS[item.tone];
          return (
            <div
              key={item.id}
              className="pointer-events-auto flex animate-fade-up items-start gap-3 rounded-2xl border border-line bg-panel p-3.5 shadow-lift"
            >
              <span className={cn("mt-0.5 rounded-full border p-1", TONES[item.tone])}>
                <Icon size={12} strokeWidth={2.5} />
              </span>
              <p className="flex-1 text-[13px] font-medium leading-5 text-ink">
                {item.message}
              </p>
              <button
                type="button"
                onClick={() => remove(item.id)}
                className="rounded-md p-1 text-muted transition-colors hover:bg-line/60 hover:text-ink"
                aria-label="Dismiss notification"
              >
                <X size={13} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const value = useContext(ToastContext);
  if (!value) throw new Error("useToast must be used inside ToastProvider");
  return value;
}
