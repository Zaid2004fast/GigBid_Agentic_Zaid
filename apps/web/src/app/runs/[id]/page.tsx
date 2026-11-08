import { useParams } from "react-router-dom";
import { api, call } from "@/lib/api/client";
import { useLoad } from "@/lib/hooks";
import { RunTimeline } from "@/components/RunTimeline";
import { ErrorState, Loading } from "@/components/States";

export default function RunPage() {
  const { id = "" } = useParams();
  const r = useLoad(() => call(api.GET("/api/runs/{thread_id}", { params: { path: { thread_id: id } } })), [id], 5000);
  const h = useLoad(() => call(api.GET("/api/runs/{thread_id}/history", { params: { path: { thread_id: id } } })), [id]);
  async function replay(cp: string) {
    const res = await call(api.POST("/api/runs/{thread_id}/replay", { params: { path: { thread_id: id }, query: { checkpoint_id: cp } } }));
    window.location.href = `/runs/${encodeURIComponent(res.key ?? id)}`;
  }
  if (r.error) return <ErrorState error={r.error} retry={r.reload} />;
  if (!r.data) return <Loading rows={4} />;
  const v = r.data.values as any;
  const nodes = Object.entries(
    (v.usage ?? []).reduce((acc: Record<string, { tokens: number; usd: number; s: number }>, u: any) => {
      const n = (acc[u.node] ??= { tokens: 0, usd: 0, s: 0 });
      n.tokens += (u.tokens_in ?? 0) + (u.tokens_out ?? 0);
      n.usd += u.cost_usd ?? 0;
      if (u.wall) n.s += u.latency_s ?? 0;
      return acc;
    }, {}),
  ) as [string, { tokens: number; usd: number; s: number }][];
  return (
    <>
      <div className="page-head">
        <div><h1 className="mono" style={{ fontSize: "1.1rem" }}>{r.data.run.thread_id}</h1>
          <p className="muted">Status <strong>{r.data.run.status}</strong>{r.data.run.attention_reason ? ` - ${r.data.run.attention_reason}` : ""}</p></div>
        <a className="btn" href={r.data.trace_url} target="_blank" rel="noreferrer">Full trace ↗</a>
      </div>
      <div className="grid grid-2">
        <RunTimeline threadId={id} initial={r.data.events as any} />
        <section className="card">
          <h2>Tokens, cost and time per node</h2>
          <div className="table-wrap"><table>
            <thead><tr><th>Node</th><th>Time</th><th>Tokens</th><th>USD</th></tr></thead>
            <tbody>{nodes.map(([n, x]) => <tr key={n}><td className="mono">{n}</td><td className="mono">{x.s.toFixed(2)}s</td><td className="mono">{x.tokens}</td><td className="mono">{x.usd.toFixed(5)}</td></tr>)}</tbody>
          </table></div>
          <h3 style={{ marginTop: 16 }}>Trace spans ({r.data.spans.length})</h3>
          <div className="table-wrap" style={{ maxHeight: 320, overflow: "auto" }}><table>
            <tbody>{r.data.spans.map((s: any) => <tr key={s.span_id}><td className="mono small">{s.name}</td><td className="small">{s.kind}</td>
              <td className="mono small">{((s.end - s.start) * 1000).toFixed(0)}ms</td><td className={`small ${s.status === "error" ? "badge danger" : ""}`}>{s.status}</td></tr>)}</tbody>
          </table></div>
        </section>
      </div>
      <section className="card" style={{ marginTop: 16 }}>
        <h2>Checkpoint history (replay from any node)</h2>
        <div className="table-wrap"><table>
          <thead><tr><th>Step</th><th>Next node</th><th>Status</th><th></th></tr></thead>
          <tbody>{(h.data ?? []).map((c: any) => (
            <tr key={c.checkpoint_id}><td className="mono">{c.step}</td><td className="mono">{c.next.join(", ") || "end"}</td><td>{c.status}</td>
              <td>{c.next.length > 0 && c.next[0] !== "approval" && <button className="small" onClick={() => replay(c.checkpoint_id)}>Replay from here</button>}</td></tr>))}</tbody>
        </table></div>
      </section>
    </>
  );
}