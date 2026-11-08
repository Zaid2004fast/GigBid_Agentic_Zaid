import { Link } from "react-router-dom";
import { api, call } from "@/lib/api/client";
import { timeAgo, useLoad } from "@/lib/hooks";
import { Empty, ErrorState, Loading } from "@/components/States";

export default function RunsPage() {
  const r = useLoad(() => call(api.GET("/api/runs")), [], 6000);
  return (
    <>
      <div className="page-head"><div><h1>Agent runs</h1><p className="muted">Every bid and conversation thread, with its trace.</p></div></div>
      {r.error && <ErrorState error={r.error} retry={r.reload} />}
      {r.loading && !r.data && <Loading />}
      {r.data && r.data.length === 0 && <Empty title="No runs yet" />}
      {r.data && r.data.length > 0 && (
        <div className="card table-wrap">
          <table>
            <thead><tr><th>Thread</th><th>Graph</th><th>Status</th><th>Latency</th><th>Tokens</th><th>Started</th></tr></thead>
            <tbody>
              {r.data.map((x) => (
                <tr key={x.thread_id}>
                  <td><Link to={`/runs/${encodeURIComponent(x.thread_id)}`} className="mono">{x.job_id ?? x.thread_id}</Link></td>
                  <td>{x.graph}</td>
                  <td><span className={`badge ${x.status === "submitted" || x.status === "sent" ? "ok" : x.status?.includes("attention") || x.status === "dead_letter" ? "danger" : "info"}`}>{x.status}</span></td>
                  <td className="mono">{x.latency_s ? `${x.latency_s.toFixed(1)}s` : "-"}</td>
                  <td className="mono">{x.tokens ?? 0}</td>
                  <td className="muted small">{timeAgo(x.started_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}