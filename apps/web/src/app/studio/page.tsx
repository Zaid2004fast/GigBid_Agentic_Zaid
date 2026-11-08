import { Link } from "react-router-dom";
import { api, call } from "@/lib/api/client";
import { timeAgo, useLoad } from "@/lib/hooks";
import { Empty, ErrorState, Loading } from "@/components/States";

export default function StudioIndex() {
  const p = useLoad(() => call(api.GET("/api/approvals")), [], 8000);
  return (
    <>
      <div className="page-head"><div><h1>Proposal studio</h1><p className="muted">Everything waiting for your approval. Pending approvals survive refreshes and restarts.</p></div></div>
      {p.error && <ErrorState error={p.error} retry={p.reload} />}
      {p.loading && !p.data && <Loading />}
      {p.data && p.data.length === 0 && <Empty title="Nothing waiting for you">New drafts appear here after GigBid analyses a job worth bidding on.</Empty>}
      <div className="stack" data-testid="approval-list">
        {(p.data ?? []).map((a) => (
          <Link key={a.thread_id} to={`/studio/${encodeURIComponent(a.thread_id)}`} className="card spread" style={{ color: "inherit" }}>
            <div>
              <span className={`badge ${a.kind === "proposal" ? "info" : "warn"}`}>{a.kind}</span>{" "}
              <strong>{a.title ?? a.job_id}</strong>
              {(a.payload as any).blocked && <span className="badge danger" style={{ marginLeft: 6 }}>blocked by compliance</span>}
            </div>
            <span className="muted small">{timeAgo(a.created_at)}</span>
          </Link>
        ))}
      </div>
    </>
  );
}