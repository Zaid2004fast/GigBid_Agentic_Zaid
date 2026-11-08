import { useState } from "react";
import { api, call } from "@/lib/api/client";
import { fmtMoney } from "@/lib/hooks";

type Props = {
  threadId: string;
  kind: "proposal" | "message";
  text: string;
  blocked: boolean;
  preview?: Record<string, any> | null;
  onDone: (msg: string) => void;
};

// Approve / edit / reject. Edits are diffed server-side, saved for style memory and re-checked
// by Compliance before they can be approved again. Approve resumes the interrupted LangGraph thread.
export function ApprovalPanel({ threadId, kind, text, blocked, preview, onDone }: Props) {
  const [mode, setMode] = useState<"view" | "edit" | "reject">("view");
  const [draft, setDraft] = useState(text);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function send(action: "approve" | "edit" | "reject") {
    setBusy(true);
    setErr(null);
    try {
      await call(api.POST("/api/approvals/{thread_id}", {
        params: { path: { thread_id: threadId } },
        body: { action, edited_text: action === "edit" ? draft : null, reason: action === "reject" ? reason : null },
      }));
      onDone(action === "approve" ? (kind === "proposal" ? "Approved - submitting as a draft" : "Approved - sending") :
             action === "edit" ? "Edit saved - re-checking compliance" : "Rejected");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card stack" aria-label="Approval">
      <h2>Your decision</h2>
      {preview && (
        <div className="comment ok" data-testid="dry-run">
          <strong>Dry run:</strong>{" "}
          {kind === "proposal"
            ? <>sends this proposal at {fmtMoney(preview.preview?.bid_amount)} and spends <strong>{preview.connects_cost ?? "?"} Connects</strong>
                {preview.connects_balance_after != null && <> (balance after: {preview.connects_balance_after})</>}. Policy v{preview.preview?.policy_version ?? "?"}.</>
            : <>sends this message to thread {preview.thread_id}.</>}
        </div>
      )}
      {blocked && <div className="comment block">Compliance blocked this draft. Edit it to fix the issue; approval is disabled until it passes.</div>}
      {mode === "edit" && (
        <label>
          <span>Edit the text the client will see</span>
          <textarea value={draft} onChange={(e) => setDraft(e.target.value)} aria-label="Edit draft" data-testid="edit-box" />
        </label>
      )}
      {mode === "reject" && (
        <label>
          <span>Why reject? (helps GigBid learn)</span>
          <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. client looks low quality" data-testid="reject-reason" />
        </label>
      )}
      {err && <div className="banner danger" role="alert">{err}</div>}
      <div className="row">
        {mode === "view" && (
          <>
            <button className="btn-primary" disabled={busy || blocked} onClick={() => send("approve")} data-testid="approve">
              {kind === "proposal" ? "Approve & submit" : "Approve & send"}
            </button>
            <button disabled={busy} onClick={() => setMode("edit")} data-testid="edit">Edit</button>
            <button className="btn-danger" disabled={busy} onClick={() => setMode("reject")} data-testid="reject">Reject</button>
          </>
        )}
        {mode === "edit" && (
          <>
            <button className="btn-primary" disabled={busy || draft.trim().length < 20} onClick={() => send("edit")} data-testid="save-edit">Save edit & re-check</button>
            <button className="btn-ghost" onClick={() => setMode("view")}>Cancel</button>
          </>
        )}
        {mode === "reject" && (
          <>
            <button className="btn-danger" disabled={busy || !reason.trim()} onClick={() => send("reject")} data-testid="confirm-reject">Reject with reason</button>
            <button className="btn-ghost" onClick={() => setMode("view")}>Cancel</button>
          </>
        )}
      </div>
      <p className="muted small">Approving never auto-sends on Upwork: live mode creates a draft you confirm on the platform.</p>
    </section>
  );
}