import { useState } from "react";

type Evidence = { item_id: string; type?: string | null; title?: string | null; snippet?: string | null; source?: string | null; date?: string | null };
export type Claim = { id: string; text: string; status: string; evidence_ids: string[]; note?: string; evidence?: Evidence[] };

// A claim in the draft. Hover / focus shows the portfolio evidence behind it (R5 made visible).
export function EvidenceHover({ text, claim, label }: { text: string; claim?: Claim; label?: string }) {
  const [open, setOpen] = useState(false);
  const status = claim?.status ?? "supported";
  return (
    <span
      className={`claim ${status}`}
      tabIndex={0}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      aria-describedby={open ? `ev-${claim?.id ?? label}` : undefined}
      data-testid="claim"
    >
      {text}
      {label && <span className="cite">{label}</span>}
      {open && (
        <span className="hover-card" role="tooltip" id={`ev-${claim?.id ?? label}`}>
          <strong>{status === "supported" ? "Backed by your portfolio" : status === "partial" ? "Partly supported" : "Not supported"}</strong>
          {claim?.note && <span className="muted"> - {claim.note}</span>}
          {(claim?.evidence ?? []).map((e) => (
            <span key={e.item_id} style={{ display: "block", marginTop: 8 }}>
              <span className="badge info">{e.type ?? "evidence"}</span> <strong>{e.title ?? e.item_id}</strong>
              {e.date && <span className="muted small"> · {e.date}</span>}
              {e.snippet && <span style={{ display: "block" }} className="muted">{e.snippet.slice(0, 260)}…</span>}
              <span className="mono muted" style={{ display: "block" }}>{e.item_id}</span>
            </span>
          ))}
          {!claim?.evidence?.length && <span className="muted" style={{ display: "block" }}>{claim?.evidence_ids?.join(", ") || "No evidence attached."}</span>}
        </span>
      )}
    </span>
  );
}