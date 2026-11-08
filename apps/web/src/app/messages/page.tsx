import { useState } from "react";
import { Link } from "react-router-dom";
import { api, call } from "@/lib/api/client";
import { timeAgo, useLoad } from "@/lib/hooks";
import { Empty, ErrorState, Loading } from "@/components/States";

export default function MessagesPage() {
  const threads = useLoad(() => call(api.GET("/api/messages/threads")), [], 10000);
  const pend = useLoad(() => call(api.GET("/api/approvals")), [], 8000);
  const [sel, setSel] = useState<string | null>(null);
  const t = useLoad(() => (sel ? call(api.GET("/api/messages/threads/{thread_id}", { params: { path: { thread_id: sel } } })) : Promise.resolve(null)), [sel]);
  const [msg, setMsg] = useState<string | null>(null);
  const pendingMsgs = (pend.data ?? []).filter((a) => a.kind === "message");

  async function draft() {
    if (!sel) return;
    const r = await call(api.POST("/api/messages/threads/{thread_id}/draft", { params: { path: { thread_id: sel } } }));
    setMsg(r.message + " - it will appear under 'Replies waiting for approval'.");
    setTimeout(pend.reload, 4000);
  }
  return (
    <>
      <div className="page-head"><div><h1>Messages</h1><p className="muted">Client threads with suggested replies. Nothing is sent until you approve.</p></div></div>
      {msg && <div className="banner ok">{msg}</div>}
      {pendingMsgs.length > 0 && (
        <section className="card stack" style={{ marginBottom: 16 }}>
          <h2>Replies waiting for approval</h2>
          {pendingMsgs.map((a) => <Link key={a.thread_id} to={`/studio/${encodeURIComponent(a.thread_id)}`}>{(a.payload as any).intent?.intent}: {a.title}</Link>)}
        </section>
      )}
      {threads.error && <ErrorState error={threads.error} retry={threads.reload} />}
      {threads.loading && !threads.data && <Loading />}
      {threads.data && threads.data.length === 0 && <Empty title="No client conversations yet">When a client replies to a proposal, the thread shows up here.</Empty>}
      <div className="grid grid-2">
        <div className="card" style={{ padding: 0 }}>
          {(threads.data ?? []).map((th) => (
            <button key={th.thread_id} className="job-row btn-ghost" style={{ width: "100%", textAlign: "left", borderRadius: 0 }} onClick={() => setSel(th.thread_id)}
                    aria-pressed={sel === th.thread_id}>
              <span><strong>{th.job_id}</strong><br /><span className="muted small">{th.count} messages · {timeAgo(th.last_at)}</span></span>
              {th.pending_approval && <span className="badge warn">reply pending</span>}
            </button>
          ))}
        </div>
        {sel && (
          <section className="card stack">
            <div className="spread"><h2>{sel}</h2><button className="btn-primary" onClick={draft} data-testid="draft-reply">Suggest a reply</button></div>
            <div className="stack" style={{ gap: 4 }}>
              {((t.data as any)?.messages ?? []).map((m: any) => <div key={m.id} className={`bubble ${m.from}`}>{m.text}</div>)}
            </div>
          </section>
        )}
      </div>
    </>
  );
}