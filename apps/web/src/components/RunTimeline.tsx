import { useRunStream, type RunEvent } from "@/lib/hooks";

// Live node-by-node progress streamed (SSE) from LangGraph's "updates" + "custom" stream modes.
export function RunTimeline({ threadId, initial }: { threadId: string; initial?: RunEvent[] }) {
  const { events, status, done } = useRunStream(threadId);
  const evs = (events.length ? events : initial ?? []).filter((e) => e.type === "update" || e.type === "interrupt");
  return (
    <section className="card" aria-live="polite">
      <div className="spread">
        <h2>Run timeline</h2>
        <span className="badge info">{!done && <span className="dot live" aria-hidden />}{status ?? "connecting"}</span>
      </div>
      {evs.length === 0 && <p className="muted">Waiting for the first node…</p>}
      <ol className="timeline">
        {evs.map((e, i) => (
          <li key={i}>
            <span className="node">{e.node ?? e.type}</span>
            <span>{e.type === "interrupt" ? "Waiting for your approval" : e.progress ?? e.summary ?? e.message ?? e.status ?? ""}</span>
            <span className="muted small mono">{e.latency_s != null ? `${e.latency_s.toFixed(2)}s` : ""}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}