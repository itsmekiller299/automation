import { useCallback, useEffect, useRef, useState } from "react";

export interface PollingResult<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  refreshing: boolean;
  updatedAt: number | null;
  refresh: () => void;
}

export function usePolling<T>(
  loader: () => Promise<T>,
  intervalMs: number,
  deps: unknown[] = [],
): PollingResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const hasLoaded = useRef(false);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  const refresh = useCallback(() => {
    setReloadKey((value) => value + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function run() {
      if (!hasLoaded.current) setLoading(true);
      setRefreshing(true);
      try {
        const next = await loaderRef.current();
        if (cancelled) return;
        setData(next);
        setError(null);
        setUpdatedAt(Date.now());
        hasLoaded.current = true;
      } catch (caught) {
        if (cancelled) return;
        setError(caught instanceof Error ? caught : new Error(String(caught)));
      } finally {
        if (!cancelled) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    }

    void run();
    const timer = intervalMs > 0 ? window.setInterval(run, intervalMs) : undefined;
    return () => {
      cancelled = true;
      if (timer) window.clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, reloadKey, ...deps]);

  return { data, error, loading, refreshing, updatedAt, refresh };
}

export function useDebounced<T>(value: T, delay = 320): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}
