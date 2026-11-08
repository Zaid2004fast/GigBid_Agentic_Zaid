import { api, call, type PipelineCard } from "@/lib/api/client";
import { fmtMoney, timeAgo, useLoad } from "@/lib/hooks";
import { ErrorState, Loading } from "@/components/States";

const STAGES = ["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"];

export default function PipelinePage() {
  const b = useLoad(() => call(api.GET("/api/pipeline")), [], 10000);
  async function refresh() {
    await call(api.POST("/api/pipeline/refresh"));
    setTimeout(b.reload, 2500);
  }
  const by: Record<string, PipelineCard[]> = Object.fromEntries(STAGES.map((s) => [s, []]));
  (b.data ?? []).forEach((c) => (by[c.stage] ??= []).push(c));
  return (
    <>
      <div className="page-head">
        <div><h1>Pipeline</h1><p className="muted">Cards move as marketplace events arrive (viewed, replied, interview, hired, lost).</p></div>
        <button onClick={refresh} data-testid="refresh-pipeline">Check marketplace now</button>
      </div>
      {b.error && <ErrorState error={b.error} retry={b.reload} />}
      {!b.data && !b.error && <Loading />}
      <div className="kanban" data-testid="kanban">
        {STAGES.map((s) => (
          <section className="lane" key={s} aria-label={s}>
            <h3><span>{s}</span><span>{by[s].length}</span></h3>
            {by[s].map((c) => (
              <div className="kcard" key={c.job_id}>
                <strong>{c.title ?? c.job_id}</strong>
                <div className="muted small">{c.category}</div>
                <div className="row small"><span>{fmtMoney(c.price)}</span>{c.connects != null && <span className="muted">{c.connects} Connects</span>}</div>
                <div className="muted small">{timeAgo(c.updated_at)}</div>
              </div>
            ))}
          </section>
        ))}
      </div>
    </>
  );
}