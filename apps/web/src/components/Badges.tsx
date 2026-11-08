import { fmtPct } from "@/lib/hooks";

export function RiskBadge({ level, risk }: { level?: string | null; risk?: number | null }) {
  const l = level ?? (risk == null ? null : risk >= 0.55 ? "high" : risk >= 0.3 ? "medium" : "low");
  if (!l) return <span className="badge">not analysed</span>;
  const cls = l === "high" ? "danger" : l === "medium" ? "warn" : "ok";
  return <span className={`badge ${cls}`} title={`risk score ${risk ?? ""}`}>{l} risk</span>;
}

export function ActionBadge({ action, status }: { action?: string | null; status?: string }) {
  if (status === "queued" || status === "running") return <span className="badge info">analysing…</span>;
  if (status === "duplicate") return <span className="badge">duplicate</span>;
  if (status === "queued_degraded") return <span className="badge warn">queued (marketplace down)</span>;
  if (status === "submitted") return <span className="badge ok">submitted</span>;
  if (!action) return <span className="badge">{status ?? "new"}</span>;
  const cls = action === "bid" ? "ok" : action === "watch" ? "warn" : "danger";
  return <span className={`badge ${cls}`}>{action === "bid" ? "bid" : action === "watch" ? "watch" : "skip"}</span>;
}

export function FitMeter({ fit }: { fit?: number | null }) {
  return (
    <div className="row" title="fit score" aria-label={`fit ${fmtPct(fit)}`}>
      <div className="meter" style={{ width: 90 }}><div style={{ width: `${Math.round((fit ?? 0) * 100)}%` }} /></div>
      <span className="small mono">{fmtPct(fit)}</span>
    </div>
  );
}