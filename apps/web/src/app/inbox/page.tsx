import { useState } from "react";
import { Link } from "react-router-dom";
import { api, call } from "@/lib/api/client";
import { fmtMoney, timeAgo, useLoad } from "@/lib/hooks";
import { ActionBadge, FitMeter, RiskBadge } from "@/components/Badges";
import { Empty, ErrorState, Loading } from "@/components/States";

export default function InboxPage() {
  const [sort, setSort] = useState<"fit" | "recent" | "risk">("fit");
  const [filter, setFilter] = useState<string>("all");
  const jobs = useLoad(() => call(api.GET("/api/jobs", { params: { query: { sort } } })), [sort], 8000);
  const [msg, setMsg] = useState<string | null>(null);

  async function scout() {
    const r = await call(api.POST("/api/jobs/scout"));
    setMsg(r.message);
    jobs.reload();
  }
  async function skip(id: string) {
    await call(api.POST("/api/jobs/{job_id}/skip", { params: { path: { job_id: id } } }));
    jobs.reload();
  }
  const rows = (jobs.data ?? []).filter((j) => filter === "all" || (filter === "bid" ? j.action === "bid" : filter === "risky" ? (j.risk ?? 0) >= 0.3 : j.status === filter));
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Job inbox</h1>
          <p className="muted">New jobs from your saved searches, ranked by fit. Risky posts are flagged before you spend Connects.</p>
        </div>
        <div className="row">
          <label className="sr-only" htmlFor="sort">Sort</label>
          <select id="sort" value={sort} onChange={(e) => setSort(e.target.value as typeof sort)} style={{ width: "auto" }}>
            <option value="fit">Best fit</option><option value="recent">Newest</option><option value="risk">Riskiest</option>
          </select>
          <label className="sr-only" htmlFor="filter">Filter</label>
          <select id="filter" value={filter} onChange={(e) => setFilter(e.target.value)} style={{ width: "auto" }}>
            <option value="all">All</option><option value="bid">Recommended bids</option><option value="awaiting_approval">Awaiting approval</option>
            <option value="risky">Risky</option><option value="skipped">Skipped</option><option value="duplicate">Duplicates</option>
          </select>
          <button className="btn-primary" onClick={scout} data-testid="scout">Scout now</button>
        </div>
      </div>
      {msg && <div className="banner ok">{msg}</div>}
      {jobs.error && <ErrorState error={jobs.error} retry={jobs.reload} />}
      {jobs.loading && !jobs.data && <Loading rows={5} label="Loading jobs" />}
      {jobs.data && rows.length === 0 && <Empty title="No jobs yet">Run your saved searches with "Scout now", or widen them in Settings.</Empty>}
      {rows.length > 0 && (
        <div className="card" style={{ padding: 0 }} data-testid="inbox-list">
          {rows.map((j) => (
            <div className="job-row" key={j.job_id}>
              <div className="stack" style={{ gap: 4 }}>
                <Link to={`/jobs/${encodeURIComponent(j.job_id)}`}><strong>{j.title}</strong></Link>
                <div className="row small muted">
                  <span>{j.category}</span><span>·</span>
                  <span>{(j.budget as any)?.type === "hourly" ? `$${(j.budget as any).min}-${(j.budget as any).max}/hr` : fmtMoney((j.budget as any)?.amount)}</span>
                  {j.duplicate_of && <span className="badge">repost of {j.duplicate_of}</span>}
                  {j.flags?.filter((f) => !["new_client"].includes(f)).slice(0, 3).map((f) => <span key={f} className="badge warn">{f.replace(/_/g, " ")}</span>)}
                </div>
              </div>
              <div className="stack" style={{ alignItems: "flex-end", gap: 6 }}>
                <div className="row"><ActionBadge action={j.action} status={j.status} /><RiskBadge level={j.risk_level} risk={j.risk} /></div>
                <FitMeter fit={j.fit} />
                <div className="row small">
                  {j.price != null && <span>{fmtMoney(j.price)}</span>}
                  {j.connects != null && <span className="muted">{j.connects} Connects</span>}
                  {j.status === "awaiting_approval" && j.thread_id && <Link to={`/studio/${encodeURIComponent(j.thread_id)}`}>Review draft →</Link>}
                  {!["skipped", "skipped_by_user", "submitted"].includes(j.status) && <button className="btn-ghost small" onClick={() => skip(j.job_id)}>Skip</button>}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}