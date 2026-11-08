import { useCallback, useEffect, useRef, useState } from "react";

export type Loadable<T> = { data: T | null; error: string | null; loading: boolean; reload: () => void };

export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = [], pollMs = 0): Loadable<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  useEffect(() => {
    let alive = true;
    setLoading(data === null);
    fn()
      .then((d) => alive && (setData(d), setError(null)))
      .catch((e: Error) => alive && setError(e.message))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  useEffect(() => {
    if (!pollMs) return;
    const id = setInterval(reload, pollMs);
    return () => clearInterval(id);
  }, [pollMs, reload]);
  return { data, error, loading, reload };
}

export type RunEvent = { id?: string; type?: string; node?: string; phase?: string; message?: string; status?: string | null; progress?: string | null; summary?: string; latency_s?: number; ts?: number };

// Server-Sent Events from the LangGraph stream bridge (/api/runs/{id}/stream).
export function useRunStream(threadId: string | undefined) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const esRef = useRef<EventSource | null>(null);
  useEffect(() => {
    if (!threadId) return;
    setEvents([]);
    setDone(false);
    const es = new EventSource(`/api/runs/${encodeURIComponent(threadId)}/stream`, { withCredentials: true });
    esRef.current = es;
    es.addEventListener("progress", (e) => setEvents((xs) => [...xs, JSON.parse((e as MessageEvent).data)]));
    es.addEventListener("status", (e) => setStatus(JSON.parse((e as MessageEvent).data).status));
    es.addEventListener("done", () => {
      setDone(true);
      es.close();
    });
    es.onerror = () => setDone(true);
    return () => es.close();
  }, [threadId]);
  return { events, status, done };
}

export const fmtMoney = (n?: number | null) => (n == null ? "-" : `$${Math.round(n).toLocaleString()}`);
export const fmtPct = (n?: number | null) => (n == null ? "-" : `${Math.round(n * 100)}%`);
export const timeAgo = (ts?: number | null) => {
  if (!ts) return "";
  const s = Math.max(1, Math.round(Date.now() / 1000 - ts));
  return s < 60 ? `${s}s ago` : s < 3600 ? `${Math.round(s / 60)}m ago` : s < 86400 ? `${Math.round(s / 3600)}h ago` : `${Math.round(s / 86400)}d ago`;
};