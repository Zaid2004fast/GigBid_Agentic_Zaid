import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, call } from "@/lib/api/client";
import { fmtMoney, fmtPct, useLoad } from "@/lib/hooks";
import { ApprovalPanel } from "@/components/ApprovalPanel";
import { EvidenceHover, type Claim } from "@/components/EvidenceHover";
import { RiskBadge } from "@/components/Badges";
import { ErrorState, Loading } from "@/components/States";

const SPLIT = /(?<=[.!?])\s+(?=[A-Z"'(\[])/;
const strip = (s: string) => s.replace(/\s*\[E\d+\]/g, "").trim();

export default function StudioPage() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const a = useLoad(() => call(api.GET("/api/approvals/{thread_id}", { params: { path: { thread_id: id } } })), [id]);
  const [toast, setToast] = useState<string | null>(null);
  const [regen, setRegen] = useState<number | null>(null);
  if (a.error) {
    return (<><ErrorState error={a.error} retry={a.reload} />
      <p><Link to={`/runs/${encodeURIComponent(id)}`}>Open the agent run</Link> to see what happened.</p></>);
  }
  if (!a.data) return <Loading rows={5} />;
  const p = a.data.payload as any;

  if (a.data.kind === "message") {
    return (
      <>
        <div className="page-head"><div><h1>Reply to client</h1><p className="muted">Intent: <strong>{p.intent?.intent}</strong> ({fmtPct(p.intent?.confidence)})</p></div></div>
        <div className="grid grid-2">
          <section className="card stack">
            <h2>Client said</h2>
            <div className="bubble client">{p.client_message}</div>
            {p.injection?.score >= 0.5 && <div className="comment block">This message contains instructions aimed at AI tools. They were removed before drafting.</div>}
            <h2>Suggested reply</h2>
            <p className="draft">{p.reply.text}</p>
            {p.reply.proposed_slots?.length > 0 && <div className="small"><strong>Interview slots offered:</strong> {p.reply.proposed_slots.map((s: any) => s.label).join("; ")}</div>}
            {p.reply.walk_away && <div className="comment block">Below your walk-away floor - GigBid recommends a smaller scope instead.</div>}
            {(p.compliance?.issues ?? []).map((i: any, k: number) => <div key={k} className={`comment ${i.action === "block" ? "block" : ""}`}>{i.message}</div>)}
          </section>
          <ApprovalPanel threadId={id} kind="message" text={p.reply.text} blocked={p.blocked} preview={p.preview}
                         onDone={(m) => { setToast(m); setTimeout(() => nav("/messages"), 900); }} />
        </div>
        {toast && <div className="banner ok" role="status">{toast}</div>}
      </>
    );
  }

  const d = p.draft;
  const claims: Claim[] = p.claims ?? [];
  const byText = new Map(claims.map((c) => [c.text, c]));
  const sentences: string[] = (d.text as string).split(SPLIT);

  async function regenerate(i: number) {
    setRegen(i);
    try {
      await call(api.POST("/api/approvals/{thread_id}/regenerate", { params: { path: { thread_id: id } }, body: { sentence_index: i } }));
      a.reload();
    } finally {
      setRegen(null);
    }
  }

  const crit = p.critique;
  const ver = p.verification;
  return (
    <>
      <div className="page-head">
        <div>
          <h1>{p.job_title}</h1>
          <div className="row small"><RiskBadge level={p.risk?.level} risk={p.risk?.risk_score} />
            <span>Bid {fmtMoney(p.price?.amount)}{p.price?.budget_type === "hourly" ? "/hr" : ""}</span>
            <span className="muted">draft v{d.version} · {d.word_count} words · {d.writer_model}</span>
            <Link to={`/jobs/${encodeURIComponent(p.job_id)}`}>Job detail</Link><Link to={`/runs/${encodeURIComponent(id)}`}>Agent run</Link></div>
        </div>
      </div>
      {toast && <div className="banner ok" role="status" data-testid="toast">{toast}</div>}
      <div className="grid grid-2">
        <div className="stack">
          <section className="card">
            <div className="spread"><h2>Draft</h2><span className="small muted">Hover a highlighted claim to see its evidence</span></div>
            <p className="draft" data-testid="draft">
              {sentences.map((s, i) => {
                const label = (s.match(/\[(E\d+)\]/) ?? [])[1];
                // match by text first, then by the evidence item the label points to
                const itemId = label ? (d.evidence_labels ?? {})[label] : undefined;
                const c = byText.get(strip(s)) ?? claims.find((x) => itemId && x.evidence_ids?.includes(itemId)) ??
                  (itemId ? { id: `lbl-${i}`, text: strip(s), status: "supported", evidence_ids: [itemId],
                              evidence: [(p.claims?.flatMap((x: Claim) => x.evidence ?? []) ?? []).find((e: any) => e.item_id === itemId)
                                         ?? { item_id: itemId }] } as Claim : undefined);
                return (
                  <span key={i}>
                    {c || label ? <EvidenceHover text={strip(s)} claim={c} label={label} /> : strip(s)}
                    {(c || label) && (
                      <button className="btn-ghost small" title="Regenerate this sentence" aria-label={`Regenerate sentence ${i + 1}`}
                              disabled={regen !== null} onClick={() => regenerate(i)} style={{ minHeight: 0, padding: "0 4px" }}>↻</button>
                    )}{" "}
                  </span>
                );
              })}
            </p>
            {d.screening_answers?.length > 0 && (
              <>
                <div className="divider" />
                <h3>Screening answers</h3>
                <ol className="small">{d.screening_answers.map((s: string, i: number) => <li key={i}>{s}</li>)}</ol>
              </>
            )}
          </section>
          <section className="card stack">
            <h2>Reviewer comments</h2>
            {ver && <div className={`comment ${ver.unsupported_after ? "block" : "ok"}`}>Claim check: {ver.claims.length} claims · unsupported {ver.unsupported_before} → {ver.unsupported_after}
              {ver.rewritten?.length ? ` · ${ver.rewritten.length} rewritten` : ""}{ver.removed?.length ? ` · ${ver.removed.length} removed` : ""}</div>}
            {crit && <div className={`comment ${crit.passed ? "ok" : ""}`}>Critic ({fmtPct(crit.score)}): {crit.issues.length ? crit.issues.join("; ") : "no issues"}</div>}
            {(p.compliance?.issues ?? []).map((i: any, k: number) => <div key={k} className={`comment ${i.action === "block" ? "block" : ""}`}>Compliance {i.rule_id}: {i.message}</div>)}
            {p.compliance && !p.compliance.issues.length && <div className="comment ok">Compliance: passes policy pack v{p.compliance.rules_version}</div>}
          </section>
        </div>
        <div className="stack">
          <ApprovalPanel threadId={id} kind="proposal" text={d.sendable_text} blocked={p.blocked} preview={p.preview}
                         onDone={(m) => { setToast(m); setTimeout(() => nav(`/runs/${encodeURIComponent(id)}`), 900); }} />
          <section className="card small">
            <h2>Why bid, and at this price?</h2>
            <ul>{(p.decision?.reasons ?? []).map((r: string, i: number) => <li key={i}>{r}</li>)}</ul>
            <p>{p.price?.rationale}</p>
          </section>
          <section className="card small">
            <h2>Risk report</h2>
            {(p.risk?.flags ?? []).map((f: any, i: number) => <div key={i}><span className="badge warn">{f.code}</span> {f.evidence}</div>)}
            {!(p.risk?.flags ?? []).length && <p className="muted">No risk signals.</p>}
          </section>
        </div>
      </div>
    </>
  );
}