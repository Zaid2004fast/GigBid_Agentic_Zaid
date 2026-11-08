import { Link, useParams } from "react-router-dom";
import { api, call } from "@/lib/api/client";
import { fmtMoney, fmtPct, useLoad } from "@/lib/hooks";
import { ActionBadge, RiskBadge } from "@/components/Badges";
import { EvidenceMatrix } from "@/components/EvidenceMatrix";
import { ErrorState, Loading } from "@/components/States";

export default function JobPage() {
  const { id = "" } = useParams();
  const d = useLoad(() => call(api.GET("/api/jobs/{job_id}", { params: { path: { job_id: id } } })), [id], 6000);
  if (d.error) return <ErrorState error={d.error} retry={d.reload} />;
  if (!d.data) return <Loading rows={4} />;
  const { job, job_spec: spec, risk, fit, decision, price } = d.data as any;
  return (
    <>
      <div className="page-head">
        <div>
          <h1>{job.title}</h1>
          <div className="row"><ActionBadge action={decision?.action} status={d.data.status} /><RiskBadge level={risk?.level} risk={risk?.risk_score} />
            <span className="muted small">{job.category}</span></div>
        </div>
        <div className="row">
          {d.data.thread_id && d.data.status === "awaiting_approval" && <Link className="btn btn-primary" to={`/studio/${encodeURIComponent(d.data.thread_id)}`}>Open proposal studio</Link>}
          {d.data.thread_id && <Link className="btn" to={`/runs/${encodeURIComponent(d.data.thread_id)}`}>Agent run</Link>}
        </div>
      </div>
      <div className="grid grid-2">
        <section className="card">
          <h2>Bid or skip?</h2>
          {decision ? (
            <>
              <p><strong>{decision.action.toUpperCase()}</strong> · p(reply) {fmtPct(decision.p_reply)} · EV {fmtMoney(decision.expected_value_usd)} for {decision.connects_cost} Connects</p>
              <ul>{decision.reasons.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul>
            </>
          ) : <p className="muted">Analysis in progress…</p>}
        </section>
        <section className="card">
          <h2>Price</h2>
          {price ? (<><p className="kpi">{fmtMoney(price.amount)}{price.budget_type === "hourly" ? "/hr" : ""}</p><p className="small">{price.rationale}</p>
            {!price.worth_connects && <div className="comment block">Not worth the Connects at your floor.</div>}</>) : <p className="muted">Priced only for recommended bids.</p>}
        </section>
        <section className="card">
          <h2>JobSpec</h2>
          {spec ? (<div className="stack small">
            <p><strong>Summary:</strong> {spec.summary}</p>
            <p><strong>Budget:</strong> {spec.budget_type} {fmtMoney(spec.budget_max)} · <strong>Timeline:</strong> {spec.timeline ?? "-"}</p>
            <p><strong>Deliverables:</strong> {spec.deliverables.join("; ") || "-"}</p>
            <p><strong>Hidden needs:</strong> {spec.hidden_needs.join("; ") || "-"}</p>
            <p><strong>Screening questions:</strong> {spec.screening_questions.length ? spec.screening_questions.join(" / ") : "none"}</p>
            <p className="muted">Extracted by: {spec.extraction}</p></div>) : <p className="muted">-</p>}
        </section>
        <section className="card">
          <h2>Risk report</h2>
          {risk ? (<div className="stack small">
            <p>Client quality {fmtPct(risk.client_quality)} · scam probability {fmtPct(risk.scam_probability)}</p>
            {risk.injection_detected && <div className="comment block">Prompt injection detected in the post and neutralised. It never reaches the writer.</div>}
            {risk.flags.map((f: any, i: number) => <div key={i} className={`comment ${f.severity === "high" ? "block" : ""}`}><strong>{f.code.replace(/_/g, " ")}</strong> - {f.evidence}</div>)}
            {!risk.flags.length && <p className="muted">No risk signals.</p>}</div>) : <p className="muted">-</p>}
        </section>
      </div>
      <section className="card" style={{ marginTop: 16 }}>
        <div className="spread"><h2>Requirement → evidence</h2>{fit && <span className="badge info">fit {fmtPct(fit.fit_score)} · retrieval {fit.variant}</span>}</div>
        <EvidenceMatrix matrix={fit?.matrix ?? []} />
      </section>
      <details className="card" style={{ marginTop: 16 }}>
        <summary>Original post (untrusted - shown as data)</summary>
        <pre className="mono" style={{ whiteSpace: "pre-wrap" }}>{job.description}</pre>
      </details>
    </>
  );
}