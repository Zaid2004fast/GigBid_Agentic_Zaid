import { api, call } from "@/lib/api/client";
import { fmtPct, useLoad } from "@/lib/hooks";
import { Empty, ErrorState, Loading } from "@/components/States";

export default function AnalyticsPage() {
  const a = useLoad(() => call(api.GET("/api/analytics")), [], 15000);
  if (a.error) return <ErrorState error={a.error} retry={a.reload} />;
  if (!a.data) return <Loading rows={4} />;
  const d = a.data as any;
  const cl = d.cost_latency;
  return (
    <>
      <div className="page-head"><div><h1>Analytics</h1><p className="muted">What your Connects bought, and what GigBid costs to run.</p></div></div>
      <div className="grid grid-3">
        <section className="card"><p className="muted small">Connects spent</p><p className="kpi">{d.connects.spent}</p><p className="small">{d.connects.replies} replies · {d.connects.connects_per_reply ?? "-"} Connects per reply</p></section>
        <section className="card"><p className="muted small">Cost per proposal</p><p className="kpi">${cl.usd_per_proposal.toFixed(4)}</p><p className="small">${cl.usd_per_job.toFixed(4)} per job analysed</p></section>
        <section className="card"><p className="muted small">p95 latency</p><p className="kpi">{cl.p95_latency_proposal_s}s</p><p className="small">per proposal · {cl.p95_latency_job_s}s per job</p></section>
      </div>
      <section className="card" style={{ marginTop: 16 }}>
        <h2>Reply and hire rate by category</h2>
        {d.by_category.length === 0 ? <Empty title="No submitted proposals yet" /> : (
          <div className="table-wrap"><table>
            <thead><tr><th>Category</th><th>Submitted</th><th>Reply rate</th><th>Hire rate</th><th>Connects</th></tr></thead>
            <tbody>{d.by_category.map((r: any) => (
              <tr key={r.category}><td>{r.category}</td><td>{r.submitted}</td>
                <td><div className="row"><div className="meter" style={{ width: 80 }}><div style={{ width: fmtPct(r.reply_rate) }} /></div>{fmtPct(r.reply_rate)}</div></td>
                <td>{fmtPct(r.hire_rate)}</td><td>{r.connects}</td></tr>))}</tbody>
          </table></div>
        )}
      </section>
      <div className="grid grid-2" style={{ marginTop: 16 }}>
        <section className="card"><h2>Top rejection reasons</h2>
          {d.top_rejections.length === 0 ? <p className="muted">No rejections yet.</p> : <ol>{d.top_rejections.map((r: any) => <li key={r.reason}>{r.reason} ({r.count})</li>)}</ol>}</section>
        <section className="card"><h2>Funnel</h2>
          <ul>{Object.entries(d.funnel).map(([k, v]) => <li key={k}>{k}: <strong>{String(v)}</strong></li>)}</ul></section>
      </div>
    </>
  );
}